"""Tests for the reply/quote action on chat messages (ticket 3f8c)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from kingdom.thread import create_thread
from kingdom.tui.widgets import MessagePanel, format_reply_text

BRANCH = "feature/test-chat"


# ---------------------------------------------------------------------------
# format_reply_text
# ---------------------------------------------------------------------------


class TestFormatReplyText:
    """Tests for the format_reply_text helper function."""

    def test_returns_at_mention_with_trailing_space(self) -> None:
        result = format_reply_text("claude")
        assert result == "@claude "

    def test_different_sender(self) -> None:
        result = format_reply_text("codex")
        assert result == "@codex "

    def test_starts_with_at(self) -> None:
        result = format_reply_text("claude")
        assert result.startswith("@")

    def test_ends_with_space(self) -> None:
        result = format_reply_text("claude")
        assert result.endswith(" ")


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

        posted: list = []
        panel.post_message = lambda msg: posted.append(msg)

        panel.on_click(self.make_click_event(shift=False))

        assert len(posted) == 1
        reply = posted[0]
        assert isinstance(reply, MessagePanel.Reply)
        assert reply.sender == "claude"
        assert reply.body == "I think we should refactor."

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

    def setup_app(self, project, tid, members=("claude",)):
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, tid, ["king", *members], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        mock_input = MagicMock()
        mock_input.text = ""
        mock_log = MagicMock()
        mock_log.query.return_value = []

        def fake_query_one(selector, *args, **kwargs):
            if selector == "#input-area":
                return mock_input
            if selector == "#message-log":
                return mock_log
            return MagicMock()

        app_instance.query_one = fake_query_one
        return app_instance, mock_input, mock_log

    def test_reply_prefills_input(self, project: Path) -> None:
        tid = "council-reply1"
        app, mock_input, _ = self.setup_app(project, tid)
        mock_input.text = ""

        event = MessagePanel.Reply(sender="claude", body="I think we should refactor.")
        app.on_message_panel_reply(event)

        loaded_text = mock_input.load_text.call_args[0][0]
        assert loaded_text == "@claude "
        assert app.reply_target == "claude"
        mock_input.focus.assert_called_once()

    def test_reply_preserves_draft(self, project: Path) -> None:
        tid = "council-reply2"
        app, mock_input, _ = self.setup_app(project, tid)
        mock_input.text = "my draft text"

        event = MessagePanel.Reply(sender="codex", body="Analysis here.")
        app.on_message_panel_reply(event)

        loaded_text = mock_input.load_text.call_args[0][0]
        assert loaded_text == "@codex my draft text"

    def test_toggle_off_clears_reply(self, project: Path) -> None:
        """Clicking same sender again clears reply target."""
        tid = "council-reply-toggle"
        app, mock_input, _ = self.setup_app(project, tid)
        mock_input.text = ""

        # First click: set target
        event = MessagePanel.Reply(sender="claude", body="Hello")
        app.on_message_panel_reply(event)
        assert app.reply_target == "claude"

        # Simulate input now has @claude
        mock_input.text = "@claude "

        # Second click on same sender: toggle off
        app.on_message_panel_reply(event)
        assert app.reply_target is None

    def test_switch_target(self, project: Path) -> None:
        """Clicking different sender switches reply target."""
        tid = "council-reply-switch"
        app, mock_input, _ = self.setup_app(project, tid, members=("claude", "codex"))
        mock_input.text = ""

        # Click claude
        app.on_message_panel_reply(MessagePanel.Reply(sender="claude", body="A"))
        assert app.reply_target == "claude"

        # Simulate input has @claude
        mock_input.text = "@claude "

        # Click codex — should switch
        app.on_message_panel_reply(MessagePanel.Reply(sender="codex", body="B"))
        assert app.reply_target == "codex"

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
