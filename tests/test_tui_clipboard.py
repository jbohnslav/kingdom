"""Tests for clipboard copy and reply actions in chat TUI."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from kingdom.tui.clipboard import ClipboardUnavailableError, copy_to_clipboard, find_clipboard_command
from kingdom.tui.widgets import MessagePanel, format_reply_text


class TestFindClipboardCommand:
    def test_darwin_pbcopy(self) -> None:
        with patch("kingdom.tui.clipboard.sys") as mock_sys, patch("kingdom.tui.clipboard.shutil") as mock_shutil:
            mock_sys.platform = "darwin"
            mock_shutil.which.return_value = "/usr/bin/pbcopy"
            assert find_clipboard_command() == ["pbcopy"]

    def test_darwin_no_pbcopy(self) -> None:
        with patch("kingdom.tui.clipboard.sys") as mock_sys, patch("kingdom.tui.clipboard.shutil") as mock_shutil:
            mock_sys.platform = "darwin"
            mock_shutil.which.return_value = None
            assert find_clipboard_command() is None

    def test_linux_xclip(self) -> None:
        with patch("kingdom.tui.clipboard.sys") as mock_sys, patch("kingdom.tui.clipboard.shutil") as mock_shutil:
            mock_sys.platform = "linux"
            mock_shutil.which.side_effect = lambda cmd: "/usr/bin/xclip" if cmd == "xclip" else None
            assert find_clipboard_command() == ["xclip", "-selection", "clipboard"]

    def test_linux_xsel_fallback(self) -> None:
        with patch("kingdom.tui.clipboard.sys") as mock_sys, patch("kingdom.tui.clipboard.shutil") as mock_shutil:
            mock_sys.platform = "linux"
            mock_shutil.which.side_effect = lambda cmd: "/usr/bin/xsel" if cmd == "xsel" else None
            assert find_clipboard_command() == ["xsel", "--clipboard", "--input"]

    def test_linux_no_clipboard(self) -> None:
        with patch("kingdom.tui.clipboard.sys") as mock_sys, patch("kingdom.tui.clipboard.shutil") as mock_shutil:
            mock_sys.platform = "linux"
            mock_shutil.which.return_value = None
            assert find_clipboard_command() is None


class TestCopyToClipboard:
    def test_success(self) -> None:
        with (
            patch("kingdom.tui.clipboard.find_clipboard_command", return_value=["pbcopy"]),
            patch("kingdom.tui.clipboard.subprocess.run") as mock_run,
        ):
            copy_to_clipboard("hello world")
            mock_run.assert_called_once_with(["pbcopy"], input=b"hello world", check=True)

    def test_no_clipboard_command_raises(self) -> None:
        with (
            patch("kingdom.tui.clipboard.find_clipboard_command", return_value=None),
            pytest.raises(ClipboardUnavailableError, match="No clipboard command found"),
        ):
            copy_to_clipboard("test")

    def test_subprocess_error_propagates(self) -> None:
        with (
            patch("kingdom.tui.clipboard.find_clipboard_command", return_value=["pbcopy"]),
            patch(
                "kingdom.tui.clipboard.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "pbcopy"),
            ),
            pytest.raises(subprocess.CalledProcessError),
        ):
            copy_to_clipboard("test")

    def test_unicode_text(self) -> None:
        with (
            patch("kingdom.tui.clipboard.find_clipboard_command", return_value=["pbcopy"]),
            patch("kingdom.tui.clipboard.subprocess.run") as mock_run,
        ):
            copy_to_clipboard("hello \u2603 world")
            mock_run.assert_called_once_with(
                ["pbcopy"],
                input="hello \u2603 world".encode(),
                check=True,
            )


# ---------------------------------------------------------------------------
# Click actions: reply (default click) and copy (shift+click)
# ---------------------------------------------------------------------------


def make_click_event(shift: bool = False) -> MagicMock:
    """Create a mock Click event with the given shift state."""
    event = MagicMock()
    event.shift = shift
    return event


SUBTITLE_HINT = "click: reply \u00b7 shift: copy"


class TestMessagePanelCopy:
    def test_member_panel_has_action_hints(self) -> None:
        """Member message panels should show reply/copy hint subtitle after mount."""
        panel = MessagePanel(sender="claude", body="Hello world")
        # on_mount sets border_subtitle for non-king messages
        panel.on_mount()
        assert panel.border_subtitle == SUBTITLE_HINT

    def test_king_panel_no_action_hints(self) -> None:
        """King message panels should not have action subtitle."""
        panel = MessagePanel(sender="king", body="Question?")
        panel.on_mount()
        # King panels have no border_subtitle set
        assert not panel.border_subtitle

    def test_shift_click_copies_body(self) -> None:
        """Shift+clicking a member panel should copy the body text."""
        panel = MessagePanel(sender="claude", body="Analysis result")
        panel.on_mount()
        panel.set_timer = MagicMock()

        with patch("kingdom.tui.widgets.copy_to_clipboard") as mock_copy:
            panel.on_click(make_click_event(shift=True))
            mock_copy.assert_called_once_with("Analysis result")
        assert panel.border_subtitle == "copied!"
        panel.set_timer.assert_called_once()

    def test_on_click_king_is_noop(self) -> None:
        """Clicking a king panel should do nothing."""
        panel = MessagePanel(sender="king", body="Question?")
        panel.on_mount()

        with patch("kingdom.tui.widgets.copy_to_clipboard") as mock_copy:
            panel.on_click(make_click_event())
            mock_copy.assert_not_called()

    def test_shift_click_clipboard_unavailable(self) -> None:
        """When clipboard is unavailable, show a clear message."""
        panel = MessagePanel(sender="claude", body="Test body")
        panel.on_mount()
        panel.set_timer = MagicMock()

        with patch("kingdom.tui.widgets.copy_to_clipboard", side_effect=ClipboardUnavailableError("No clipboard")):
            panel.on_click(make_click_event(shift=True))
        assert panel.border_subtitle == "clipboard unavailable"
        panel.set_timer.assert_called_once()

    def test_shift_click_subprocess_error(self) -> None:
        """When subprocess fails, show a clear error."""
        panel = MessagePanel(sender="claude", body="Test body")
        panel.on_mount()
        panel.set_timer = MagicMock()

        with patch(
            "kingdom.tui.widgets.copy_to_clipboard",
            side_effect=subprocess.CalledProcessError(1, "pbcopy"),
        ):
            panel.on_click(make_click_event(shift=True))
        assert panel.border_subtitle == "copy failed"
        panel.set_timer.assert_called_once()

    def test_reset_subtitle(self) -> None:
        """reset_subtitle should restore the action hints."""
        panel = MessagePanel(sender="claude", body="Test")
        panel.on_mount()
        panel.border_subtitle = "copied!"
        panel.reset_subtitle()
        assert panel.border_subtitle == SUBTITLE_HINT


class TestMessagePanelReply:
    """Tests for the click-to-reply action on MessagePanel."""

    def test_click_posts_reply_message(self) -> None:
        """Regular click on a member panel should post a Reply message."""
        panel = MessagePanel(sender="claude", body="I think we should refactor.")
        panel.on_mount()
        panel.set_timer = MagicMock()

        posted: list = []
        panel.post_message = lambda msg: posted.append(msg)

        panel.on_click(make_click_event(shift=False))

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

        panel.on_click(make_click_event(shift=False))
        assert posted == []

    def test_reply_message_attributes(self) -> None:
        """Reply message should carry sender and body."""
        reply = MessagePanel.Reply(sender="codex", body="Here is my analysis.")
        assert reply.sender == "codex"
        assert reply.body == "Here is my analysis."


class TestCmdCopy:
    """Tests for the /copy slash command in ChatApp."""

    def setup_method(self) -> None:
        from kingdom.thread import Message

        self.messages = [
            Message(sequence=1, from_="king", to="all", body="What do you think?", timestamp="2026-01-01T00:00:00Z"),
            Message(
                sequence=2, from_="claude", to="king", body="Here is my analysis.", timestamp="2026-01-01T00:01:00Z"
            ),
            Message(
                sequence=3, from_="codex", to="king", body="I agree with claude.", timestamp="2026-01-01T00:02:00Z"
            ),
        ]

    def make_app_mock(self):
        app = MagicMock()
        app.base = "/tmp/test"
        app.branch = "test"
        app.thread_id = "council-test"
        app.show_system_message = MagicMock()
        return app

    def test_copy_last_member_message(self) -> None:
        from kingdom.tui import app as app_module

        mock_app = self.make_app_mock()
        with (
            patch.object(app_module, "list_messages", return_value=self.messages),
            patch("kingdom.tui.clipboard.copy_to_clipboard") as mock_copy,
        ):
            app_module.ChatApp.cmd_copy(mock_app, "")
            mock_copy.assert_called_once_with("I agree with claude.")
            mock_app.show_system_message.assert_called_once()
            assert "Copied" in mock_app.show_system_message.call_args[0][0]

    def test_copy_specific_member(self) -> None:
        from kingdom.tui import app as app_module

        mock_app = self.make_app_mock()
        with (
            patch.object(app_module, "list_messages", return_value=self.messages),
            patch("kingdom.tui.clipboard.copy_to_clipboard") as mock_copy,
        ):
            app_module.ChatApp.cmd_copy(mock_app, "claude")
            mock_copy.assert_called_once_with("Here is my analysis.")

    def test_copy_no_messages(self) -> None:
        from kingdom.tui import app as app_module

        mock_app = self.make_app_mock()
        king_only = [self.messages[0]]
        with patch.object(app_module, "list_messages", return_value=king_only):
            app_module.ChatApp.cmd_copy(mock_app, "")
            mock_app.show_system_message.assert_called_once_with("No messages to copy.")

    def test_copy_unknown_member(self) -> None:
        from kingdom.tui import app as app_module

        mock_app = self.make_app_mock()
        with patch.object(app_module, "list_messages", return_value=self.messages):
            app_module.ChatApp.cmd_copy(mock_app, "gemini")
            mock_app.show_system_message.assert_called_once_with("No messages from gemini.")


class TestFormatReplyText:
    """Tests for the format_reply_text helper function."""

    def test_returns_at_mention_with_trailing_space(self) -> None:
        result = format_reply_text("claude")
        assert result == "@claude "

    def test_different_sender(self) -> None:
        result = format_reply_text("codex")
        assert result == "@codex "
