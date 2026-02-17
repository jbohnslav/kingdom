"""Chat message widgets for the TUI.

MessagePanel — finalized message (king or member), rendered as Markdown.
StreamingPanel — in-progress response, updates as tokens arrive.
WaitingPanel — placeholder before streaming starts.
ErrorPanel — error or timeout display.
ThinkingPanel — collapsible thinking/reasoning tokens.
"""

from __future__ import annotations

import time

from rich.markdown import Markdown as RichMarkdown
from textual.widgets import Static

# Fixed colors for known council members.
DEFAULT_MEMBER_COLORS: dict[str, str] = {
    "claude": "cyan",
    "codex": "green",
    "cursor": "magenta",
}

# Fallback palette for unknown members, indexed by stable hash.
FALLBACK_COLORS = [
    "yellow",
    "blue",
    "red",
    "cyan",
    "green",
    "magenta",
]


def color_for_member(name: str) -> str:
    """Return a deterministic color for a member name."""
    if name in DEFAULT_MEMBER_COLORS:
        return DEFAULT_MEMBER_COLORS[name]
    # Stable hash (not affected by PYTHONHASHSEED randomization)
    idx = sum(ord(c) for c in name) % len(FALLBACK_COLORS)
    return FALLBACK_COLORS[idx]


class MessagePanel(Static):
    """A finalized message rendered as Markdown inside a bordered panel."""

    DEFAULT_CSS = """
    MessagePanel {
        margin: 0 1;
        padding: 0 1;
        border: round $secondary;
    }
    MessagePanel.king {
        border: none;
        color: $text-muted;
    }
    """

    def __init__(self, sender: str, body: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.body = body

    def compose_text(self) -> str:
        """Format the display text (sender shown in border title, not body)."""
        return self.body

    def on_mount(self) -> None:
        if self.sender == "king":
            self.add_class("king")
        else:
            color = color_for_member(self.sender)
            self.styles.border = ("round", color)
            self.border_title = self.sender
        self.update(RichMarkdown(self.compose_text()))


class StreamingPanel(Static):
    """An in-progress response that updates as tokens stream in."""

    DEFAULT_CSS = """
    StreamingPanel {
        margin: 0 1;
        padding: 0 1;
        border: round $secondary;
    }
    """

    def __init__(self, sender: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.content_text = ""

    def on_mount(self) -> None:
        color = color_for_member(self.sender)
        self.styles.border = ("round", color)
        self.update_title()

    def update_title(self) -> None:
        n = len(self.content_text)
        self.border_title = f"{self.sender} (streaming · {n:,} chars)"

    def update_content(self, text: str) -> None:
        """Replace the streamed text and refresh the display."""
        self.content_text = text
        self.update_title()
        self.update(text + "\u258d")  # ▍ cursor


class WaitingPanel(Static):
    """A collapsed placeholder shown before streaming starts."""

    DEFAULT_CSS = """
    WaitingPanel {
        margin: 0 1;
        padding: 0;
        border: dashed $secondary;
        height: 1;
    }
    """

    def __init__(self, sender: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sender = sender

    def on_mount(self) -> None:
        color = color_for_member(self.sender)
        self.styles.border = ("dashed", color)
        self.border_title = f"{self.sender} — waiting..."


class ErrorPanel(Static):
    """An error or timeout display with red border."""

    DEFAULT_CSS = """
    ErrorPanel {
        margin: 0 1;
        padding: 0 1;
        border: round red;
    }
    """

    def __init__(self, sender: str, error: str, timed_out: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.error = error
        self.timed_out = timed_out

    def on_mount(self) -> None:
        label = "timed out" if self.timed_out else "errored"
        self.border_title = f"{self.sender} — {label}"
        self.styles.border = ("round", "red")
        self.update(RichMarkdown(self.error))


class ThinkingPanel(Static):
    """Collapsible panel for thinking/reasoning tokens.

    Starts expanded while thinking streams in.  Auto-collapses on first answer
    token into a one-line summary.  Click or Enter toggles expanded/collapsed.
    Once the user manually toggles, auto-collapse is disabled (user_pinned).
    """

    DEFAULT_CSS = """
    ThinkingPanel {
        margin: 0 1;
        padding: 0 1;
        border: dashed $secondary;
        color: $text-muted;
    }
    ThinkingPanel.collapsed {
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self, sender: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.thinking_text = ""
        self.expanded = True
        self.user_pinned = False
        self.start_time = time.monotonic()

    def on_mount(self) -> None:
        color = color_for_member(self.sender)
        self.styles.border = ("dashed", color)
        self.update_display()

    def on_click(self) -> None:
        """Toggle expanded/collapsed on click."""
        self.user_pinned = True
        self.expanded = not self.expanded
        if self.expanded:
            self.remove_class("collapsed")
        else:
            self.add_class("collapsed")
        self.update_display()

    def update_thinking(self, text: str) -> None:
        """Update with new accumulated thinking text."""
        self.thinking_text = text
        if self.expanded:
            self.update_display()

    def collapse(self) -> None:
        """Auto-collapse (called when answer tokens start arriving)."""
        if self.user_pinned:
            return
        self.expanded = False
        self.add_class("collapsed")
        self.update_display()

    def update_display(self) -> None:
        """Refresh the rendered content based on expanded/collapsed state."""
        n = len(self.thinking_text)
        elapsed = time.monotonic() - self.start_time
        if self.expanded:
            self.border_title = f"{self.sender} thinking · {n:,} chars · {elapsed:.1f}s"
            self.update(self.thinking_text + "\u258d")  # ▍ cursor
        else:
            self.border_title = f"\u25b6 {self.sender} thinking · {n:,} chars · {elapsed:.1f}s"
            self.update("")
