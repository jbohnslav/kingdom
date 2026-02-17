"""Clipboard utilities for the chat TUI.

Provides a cross-platform copy-to-clipboard function using system commands
(pbcopy on macOS, xclip/xsel on Linux). No third-party dependencies.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


class ClipboardUnavailableError(Exception):
    """Raised when no clipboard command is available."""


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard.

    Uses pbcopy on macOS, xclip or xsel on Linux/other.

    Raises:
        ClipboardUnavailableError: If no clipboard command is found.
        subprocess.CalledProcessError: If the clipboard command fails.
    """
    cmd = find_clipboard_command()
    if cmd is None:
        raise ClipboardUnavailableError("No clipboard command found. Install xclip or xsel, or run on macOS.")
    subprocess.run(cmd, input=text.encode("utf-8"), check=True)


def find_clipboard_command() -> list[str] | None:
    """Return the clipboard command for this platform, or None if unavailable."""
    if sys.platform == "darwin":
        if shutil.which("pbcopy"):
            return ["pbcopy"]
    else:
        # Linux / other: try xclip first, then xsel
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]
    return None
