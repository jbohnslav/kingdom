"""Chat message widgets for the TUI.

MessagePanel — finalized message (king or member), rendered as Markdown.
StreamingPanel — in-progress response, updates as tokens arrive.
WaitingPanel — placeholder before streaming starts.
ErrorPanel — error or timeout display.
"""

from __future__ import annotations

from textual.widgets import Static

# Deterministic color palette indexed by member name hash.
MEMBER_COLORS = [
    "cyan",
    "green",
    "magenta",
    "yellow",
    "blue",
    "red",
]


def color_for_member(name: str) -> str:
    """Return a deterministic color for a member name."""
    idx = hash(name) % len(MEMBER_COLORS)
    return MEMBER_COLORS[idx]


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
        """Format the display text."""
        return f"**{self.sender}**\n\n{self.body}"

    def on_mount(self) -> None:
        if self.sender == "king":
            self.add_class("king")
        else:
            color = color_for_member(self.sender)
            self.styles.border = ("round", color)
            self.border_title = self.sender
        self.update(self.compose_text())


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
        border: dashed $text-muted;
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
        self.update(self.error)
