"""Chat message widgets for the TUI.

MessagePanel — finalized message (king or member), rendered as Markdown.
StreamingPanel — in-progress response, updates as tokens arrive.
WaitingPanel — placeholder before streaming starts.
ErrorPanel — error or timeout display.
ThinkingPanel — collapsible thinking/reasoning tokens.
CommandHintBar — shows matching slash commands as you type.
"""

from __future__ import annotations

import subprocess
import time

from rich.markdown import Markdown as RichMarkdown
from textual.widgets import Static

from kingdom.tui.clipboard import ClipboardUnavailableError, copy_to_clipboard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-friendly duration string.

    Under 60 s  -> "12.3s"
    60 s+       -> "1m 23s"
    60 min+     -> "1h 2m 3s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    total = int(seconds)
    if total < 3600:
        m, s = divmod(total, 60)
        return f"{m}m {s}s"
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}h {m}m {s}s"


# Brand-aware colors for known council members.
#
# Rationale:
#   claude  — Anthropic brand orange (warm amber, close to the Claude logo
#             mark; #d97706 is a readable warm orange on both dark and light
#             terminal backgrounds).
#   codex   — OpenAI brand green (#19c37d is the ChatGPT/OpenAI accent
#             green, readable and distinctive from orange/blue).
#   cursor  — Cursor brand blue (dodgerblue; Cursor's logo uses a bright
#             blue accent — since the logo itself is mostly black/white, blue
#             gives a clear, readable identity in the terminal).
#
# Adding a new member?  Pick the closest readable, terminal-safe brand color.
# If the brand palette is mostly black/white, choose a distinctive hue that
# won't collide with existing entries.  Both CSS named colors and hex values
# work (Textual accepts either).
BRAND_MEMBER_COLORS: dict[str, str] = {
    "claude": "#d97706",
    "codex": "#19c37d",
    "cursor": "dodgerblue",
}

# Fallback palette for unknown members, indexed by stable hash.
# Deliberately avoids orange, green, and blue tones so unknown members
# remain visually distinct from brand-colored members.  Chosen to be
# readable on both dark and light terminal backgrounds.
FALLBACK_COLORS = [
    "magenta",
    "yellow",
    "red",
    "cyan",
    "mediumpurple",
    "coral",
    "gold",
    "orchid",
    "salmon",
    "turquoise",
    "violet",
    "hotpink",
    "khaki",
    "tomato",
    "deeppink",
    "darkturquoise",
]


def color_for_member(name: str) -> str:
    """Return a deterministic color for a member name.

    Known members get their brand color from BRAND_MEMBER_COLORS.
    Unknown members fall back to a stable hash into FALLBACK_COLORS
    (not affected by PYTHONHASHSEED randomization).
    """
    if name in BRAND_MEMBER_COLORS:
        return BRAND_MEMBER_COLORS[name]
    idx = sum(ord(c) for c in name) % len(FALLBACK_COLORS)
    return FALLBACK_COLORS[idx]


class MessagePanel(Static):
    """A finalized message rendered as Markdown inside a bordered panel.

    Click on a council member's message to copy it to the clipboard.
    """

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
            self.border_subtitle = "click to copy"
        self.update(RichMarkdown(self.compose_text()))

    def on_click(self) -> None:
        """Copy message body to clipboard on click."""
        if self.sender == "king":
            return
        try:
            copy_to_clipboard(self.body)
            self.border_subtitle = "copied!"
        except ClipboardUnavailableError:
            self.border_subtitle = "clipboard unavailable"
        except subprocess.CalledProcessError:
            self.border_subtitle = "copy failed"
        self.set_timer(2.0, self.reset_subtitle)

    def reset_subtitle(self) -> None:
        """Reset subtitle back to the copy hint after feedback timeout."""
        self.border_subtitle = "click to copy"


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
            self.border_title = f"{self.sender} thinking · {n:,} chars · {format_elapsed(elapsed)}"
            self.update(self.thinking_text + "\u258d")  # ▍ cursor
        else:
            self.border_title = f"\u25b6 {self.sender} thinking · {n:,} chars · {format_elapsed(elapsed)}"
            self.update("")
