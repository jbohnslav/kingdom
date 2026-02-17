"""Tests for clipboard copy action in chat TUI."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from kingdom.tui.clipboard import ClipboardUnavailableError, copy_to_clipboard, find_clipboard_command
from kingdom.tui.widgets import MessagePanel


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


class TestMessagePanelCopy:
    def test_member_panel_has_copy_hint(self) -> None:
        """Member message panels should show 'click to copy' subtitle after mount."""
        panel = MessagePanel(sender="claude", body="Hello world")
        # on_mount sets border_subtitle for non-king messages
        panel.on_mount()
        assert panel.border_subtitle == "click to copy"

    def test_king_panel_no_copy_hint(self) -> None:
        """King message panels should not have copy subtitle."""
        panel = MessagePanel(sender="king", body="Question?")
        panel.on_mount()
        # King panels have no border_subtitle set
        assert not panel.border_subtitle

    def test_on_click_copies_body(self) -> None:
        """Clicking a member panel should copy the body text."""
        panel = MessagePanel(sender="claude", body="Analysis result")
        panel.on_mount()
        # Mock timer to prevent Textual-internal timer setup
        panel.set_timer = MagicMock()

        with patch("kingdom.tui.widgets.copy_to_clipboard") as mock_copy:
            panel.on_click()
            mock_copy.assert_called_once_with("Analysis result")
        assert panel.border_subtitle == "copied!"
        panel.set_timer.assert_called_once()

    def test_on_click_king_is_noop(self) -> None:
        """Clicking a king panel should do nothing."""
        panel = MessagePanel(sender="king", body="Question?")
        panel.on_mount()

        with patch("kingdom.tui.widgets.copy_to_clipboard") as mock_copy:
            panel.on_click()
            mock_copy.assert_not_called()

    def test_on_click_clipboard_unavailable(self) -> None:
        """When clipboard is unavailable, show a clear message."""
        panel = MessagePanel(sender="claude", body="Test body")
        panel.on_mount()
        panel.set_timer = MagicMock()

        with patch("kingdom.tui.widgets.copy_to_clipboard", side_effect=ClipboardUnavailableError("No clipboard")):
            panel.on_click()
        assert panel.border_subtitle == "clipboard unavailable"
        panel.set_timer.assert_called_once()

    def test_on_click_subprocess_error(self) -> None:
        """When subprocess fails, show a clear error."""
        panel = MessagePanel(sender="claude", body="Test body")
        panel.on_mount()
        panel.set_timer = MagicMock()

        with patch(
            "kingdom.tui.widgets.copy_to_clipboard",
            side_effect=subprocess.CalledProcessError(1, "pbcopy"),
        ):
            panel.on_click()
        assert panel.border_subtitle == "copy failed"
        panel.set_timer.assert_called_once()

    def test_reset_subtitle(self) -> None:
        """reset_subtitle should restore the copy hint."""
        panel = MessagePanel(sender="claude", body="Test")
        panel.on_mount()
        panel.border_subtitle = "copied!"
        panel.reset_subtitle()
        assert panel.border_subtitle == "click to copy"
