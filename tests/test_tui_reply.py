"""Tests for the reply/quote action on chat messages (ticket 3f8c)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kingdom.state import ensure_branch_layout
from kingdom.thread import create_thread
from kingdom.tui.widgets import MessagePanel, format_reply_text

BRANCH = "feature/test-chat"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    return tmp_path


# ---------------------------------------------------------------------------
# format_reply_text
# ---------------------------------------------------------------------------


class TestFormatReplyText:
    """Tests for the format_reply_text helper function."""

    def test_single_line_body(self) -> None:
        result = format_reply_text("claude", "Short answer")
        assert result == "@claude\n> Short answer\n\n"

    def test_multi_line_body(self) -> None:
        body = "Line one\nLine two\nLine three"
        result = format_reply_text("codex", body)
        assert result == "@codex\n> Line one\n> Line two\n> Line three\n\n"

    def test_long_body_truncated(self) -> None:
        body = "\n".join(f"Line {i}" for i in range(10))
        result = format_reply_text("claude", body, max_quote_lines=4)
        lines = result.splitlines()
        assert lines[0] == "@claude"
        assert lines[1] == "> Line 0"
        assert lines[4] == "> Line 3"
        assert lines[5] == "> ..."
        assert result.endswith("\n\n")

    def test_body_exactly_at_limit(self) -> None:
        body = "A\nB\nC\nD"
        result = format_reply_text("codex", body, max_quote_lines=4)
        assert "> ..." not in result
        assert "> A" in result
        assert "> D" in result

    def test_body_one_over_limit(self) -> None:
        body = "A\nB\nC\nD\nE"
        result = format_reply_text("codex", body, max_quote_lines=4)
        assert "> ..." in result
        assert "> E" not in result

    def test_whitespace_stripped(self) -> None:
        body = "  \n  Hello\nWorld  \n  "
        result = format_reply_text("claude", body)
        assert result.startswith("@claude\n>")

    def test_empty_body(self) -> None:
        result = format_reply_text("claude", "")
        assert result.startswith("@claude\n")
        assert result.endswith("\n\n")

    def test_ends_with_double_newline(self) -> None:
        result = format_reply_text("claude", "Hello")
        assert result.endswith("\n\n")

    def test_custom_max_quote_lines(self) -> None:
        body = "A\nB\nC\nD\nE\nF"
        result = format_reply_text("claude", body, max_quote_lines=2)
        lines = result.splitlines()
        assert lines[0] == "@claude"
        assert lines[1] == "> A"
        assert lines[2] == "> B"
        assert lines[3] == "> ..."


# ---------------------------------------------------------------------------
# MessagePanel.Reply message
# ---------------------------------------------------------------------------


class TestMessagePanelReply:
    """Tests for the click-to-reply action on MessagePanel."""

    def make_click_event(self, shift: bool = False) -> MagicMock:
        event = MagicMock()
        event.shift = shift
        return event

    def test_click_posts_reply_message(self) -> None:
        """Regular click on a member panel should post a Reply message."""
        panel = MessagePanel(sender="claude", body="I think we should refactor.")
        panel.on_mount()
        panel.set_timer = MagicMock()

        posted: list = []
        panel.post_message = lambda msg: posted.append(msg)

        panel.on_click(self.make_click_event(shift=False))

        assert len(posted) == 1
        reply = posted[0]
        assert isinstance(reply, MessagePanel.Reply)
        assert reply.sender == "claude"
        assert reply.body == "I think we should refactor."
        assert panel.border_subtitle == "replying..."

    def test_click_on_king_does_not_post_reply(self) -> None:
        """Clicking a king message should not post a Reply."""
        panel = MessagePanel(sender="king", body="What do you think?")
        panel.on_mount()

        posted: list = []
        panel.post_message = lambda msg: posted.append(msg)

        panel.on_click(self.make_click_event(shift=False))
        assert posted == []

    def test_shift_click_copies_not_replies(self) -> None:
        """Shift+click should copy, not reply."""
        panel = MessagePanel(sender="claude", body="Analysis result")
        panel.on_mount()
        panel.set_timer = MagicMock()

        posted: list = []
        panel.post_message = lambda msg: posted.append(msg)

        from unittest.mock import patch

        with patch("kingdom.tui.widgets.copy_to_clipboard"):
            panel.on_click(self.make_click_event(shift=True))

        # Should not have posted Reply
        assert not any(isinstance(m, MessagePanel.Reply) for m in posted)
        assert panel.border_subtitle == "copied!"

    def test_reply_message_attributes(self) -> None:
        """Reply message should carry sender and body."""
        reply = MessagePanel.Reply(sender="codex", body="Here is my analysis.")
        assert reply.sender == "codex"
        assert reply.body == "Here is my analysis."

    def test_subtitle_hint_mentions_reply(self) -> None:
        """Border subtitle should mention reply."""
        panel = MessagePanel(sender="claude", body="Hello")
        panel.on_mount()
        assert "reply" in panel.border_subtitle


# ---------------------------------------------------------------------------
# ChatApp.on_message_panel_reply handler
# ---------------------------------------------------------------------------


class TestReplyHandler:
    """Test the on_message_panel_reply handler in ChatApp."""

    def test_reply_prefills_input(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-reply1"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        mock_input = MagicMock()
        mock_input.text = ""
        app_instance.query_one = MagicMock(return_value=mock_input)

        event = MessagePanel.Reply(sender="claude", body="I think we should refactor.")
        app_instance.on_message_panel_reply(event)

        loaded_text = mock_input.load_text.call_args[0][0]
        assert loaded_text.startswith("@claude\n")
        assert "> I think we should refactor." in loaded_text
        assert loaded_text.endswith("\n\n")
        mock_input.focus.assert_called_once()

    def test_reply_preserves_draft(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-reply2"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        mock_input = MagicMock()
        mock_input.text = "my draft text"
        app_instance.query_one = MagicMock(return_value=mock_input)

        event = MessagePanel.Reply(sender="codex", body="Analysis here.")
        app_instance.on_message_panel_reply(event)

        loaded_text = mock_input.load_text.call_args[0][0]
        assert "@codex" in loaded_text
        assert "> Analysis here." in loaded_text
        assert "my draft text" in loaded_text

    def test_reply_truncates_long(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-reply3"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        mock_input = MagicMock()
        mock_input.text = ""
        app_instance.query_one = MagicMock(return_value=mock_input)

        long_body = "\n".join(f"Line {i}" for i in range(10))
        event = MessagePanel.Reply(sender="claude", body=long_body)
        app_instance.on_message_panel_reply(event)

        loaded_text = mock_input.load_text.call_args[0][0]
        assert "> ..." in loaded_text
        assert "> Line 0" in loaded_text
        assert "> Line 3" in loaded_text
        assert "> Line 4" not in loaded_text

    def test_help_mentions_reply(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-reply-help"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/help")
        msg = app_instance.show_system_message.call_args[0][0]
        assert "reply" in msg.lower()
        assert "shift+click" in msg.lower()
