"""Chat message widgets for the TUI.

MessagePanel — finalized message (king or member), rendered as Markdown.
StreamingPanel — in-progress response, updates as tokens arrive.
WaitingPanel — placeholder before streaming starts.
ErrorPanel — error or timeout display.
ThinkingPanel — collapsible thinking/reasoning tokens.
CommandHintBar — shows matching slash commands as you type.
"""

from __future__ import annotations

import re
import subprocess
import time

from rich.markdown import Markdown as RichMarkdown
from rich.segment import Segment
from rich.style import Style
from textual.message import Message
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


def format_reply_text(sender: str) -> str:
    """Build reply prefix: ``@sender `` with a trailing space.

    Keeps the input clean — the user types their reply directly after the
    @mention instead of having to delete a multi-line quoted block.
    """
    return f"@{sender} "


# Brand-aware colors for known council members.
#
# Rationale:
#   claude  — Anthropic brand orange (warm amber, close to the Claude logo
#             mark; #d97706 is a readable warm orange on both dark and light
#             terminal backgrounds).
#   codex   — OpenAI brand green (#19c37d is the ChatGPT/OpenAI accent
#             green, readable and distinctive from orange/blue).
#
# Adding a new member?  Pick the closest readable, terminal-safe brand color.
# If the brand palette is mostly black/white, choose a distinctive hue that
# won't collide with existing entries.  Both CSS named colors and hex values
# work (Textual accepts either).
BRAND_MEMBER_COLORS: dict[str, str] = {
    "claude": "#d97706",
    "codex": "#19c37d",
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


class ColoredMentionMarkdown:
    """Rich renderable that renders Markdown with @mentions in member colors.

    Wraps RichMarkdown and intercepts rendered Segments, splitting any that
    contain @member tokens and applying the member's brand color + bold style.
    """

    def __init__(self, body: str, member_names: list[str]) -> None:
        self.body = body
        # Build a color lookup for known names plus special tokens
        self.member_colors: dict[str, str] = {}
        for name in member_names:
            self.member_colors[name] = color_for_member(name)
        self.member_colors["all"] = "white"
        self.member_colors["king"] = "white"
        # Pre-compile pattern
        if self.member_colors:
            names = "|".join(re.escape(n) for n in self.member_colors)
            self.pattern: re.Pattern[str] | None = re.compile(rf"(?<!\w)@({names})(?!\w)")
        else:
            self.pattern = None

    def __rich_console__(self, console, options):
        md = RichMarkdown(self.body)
        for segment in md.__rich_console__(console, options):
            if not isinstance(segment, Segment) or not self.pattern:
                yield segment
                continue

            text = segment.text
            style = segment.style or Style()

            if "@" not in text:
                yield segment
                continue

            parts = self.pattern.split(text)
            if len(parts) == 1:
                yield segment
                continue

            # parts alternates: [before, captured_name, after, ...]
            for i, part in enumerate(parts):
                if not part:
                    continue
                if i % 2 == 1:
                    color = self.member_colors.get(part, "white")
                    mention_style = style + Style(color=color, bold=True)
                    yield Segment(f"@{part}", mention_style)
                else:
                    yield Segment(part, style)


class MessagePanel(Static):
    """A finalized message rendered as Markdown inside a bordered panel.

    Click on a council member's message to reply (prefills input with quote
    and @mention).  Shift+click copies the message to the clipboard.
    """

    class Reply(Message):
        """Posted when the user clicks a member message to reply."""

        def __init__(self, sender: str, body: str) -> None:
            super().__init__()
            self.sender = sender
            self.body = body

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

    def __init__(self, sender: str, body: str, member_names: list[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sender = sender
        self.body = body
        self.member_names: list[str] = member_names or []

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
            self.border_subtitle = "click: reply \u00b7 shift: copy"
        if self.member_names:
            self.update(ColoredMentionMarkdown(self.compose_text(), self.member_names))
        else:
            self.update(RichMarkdown(self.compose_text()))

    def on_click(self, event) -> None:
        """Handle click: reply (default) or copy (shift)."""
        if self.sender == "king":
            return
        if event.shift:
            self.do_copy()
        else:
            self.post_message(self.Reply(sender=self.sender, body=self.body))
            self.border_subtitle = "replying..."
            self.set_timer(1.5, self.reset_subtitle)

    def do_copy(self) -> None:
        """Copy message body to the system clipboard."""
        try:
            copy_to_clipboard(self.body)
            self.border_subtitle = "copied!"
        except ClipboardUnavailableError:
            self.border_subtitle = "clipboard unavailable"
        except subprocess.CalledProcessError:
            self.border_subtitle = "copy failed"
        self.set_timer(2.0, self.reset_subtitle)

    def reset_subtitle(self) -> None:
        """Reset subtitle back to the action hints after feedback timeout."""
        self.border_subtitle = "click: reply \u00b7 shift: copy"


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
        self.border_title = f"{self.sender} (streaming \u00b7 {n:,} chars)"

    def update_content(self, text: str) -> None:
        """Replace the streamed text and refresh the display."""
        self.content_text = text
        self.update_title()
        self.update(text + "\u258d")  # cursor


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
        self.border_title = f"{self.sender} \u2014 waiting..."


def format_error_body(error: str, sender: str, timed_out: bool, interrupted: bool) -> str:
    """Build a user-friendly error body with context and retry hint.

    Extracts the meaningful part of the error and appends an actionable
    suggestion so the user knows what to try next.
    """
    if interrupted:
        return error  # Already says "*Interrupted*", no extra noise needed

    # Extract the useful detail from the marker format *Error: ...*
    detail = error
    if detail.startswith("*Error:") and detail.endswith("*"):
        detail = detail[len("*Error:") :].rstrip("*").strip()
    elif detail.startswith("*") and detail.endswith("*"):
        detail = detail.strip("* ").strip()

    lines: list[str] = []
    if timed_out:
        lines.append(f"**Timed out** — {detail}")
        lines.append("")
        lines.append(f"Retry: send the message again or `@{sender}` to retry just this member.")
    elif "empty response" in error.lower():
        lines.append("**Empty response** — the agent returned no text.")
        lines.append("")
        lines.append(f"Retry: rephrase your question or `@{sender}` to try again.")
    else:
        lines.append(f"**Error** — {detail}")
        lines.append("")
        lines.append("Retry: send the message again. If it persists, check agent config with `kd council status`.")

    return "\n".join(lines)


class ErrorPanel(Static):
    """An error or timeout display with context and retry hints.

    Shows what failed (timeout, error detail, interruption) and suggests
    retry actions so the user knows how to recover.
    """

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
        interrupted = "*Interrupted" in self.error or "*[Interrupted" in self.error

        if interrupted:
            label = "interrupted"
            self.styles.border = ("round", "yellow")
        elif self.timed_out:
            label = "timed out"
            self.styles.border = ("round", "red")
        else:
            label = "error"
            self.styles.border = ("round", "red")

        self.border_title = f"{self.sender} — {label}"
        body = format_error_body(self.error, self.sender, self.timed_out, interrupted)
        self.update(RichMarkdown(body))


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
            self.border_title = f"{self.sender} thinking \u00b7 {n:,} chars \u00b7 {format_elapsed(elapsed)}"
            self.update(self.thinking_text + "\u258d")  # cursor
        else:
            self.border_title = f"\u25b6 {self.sender} thinking \u00b7 {n:,} chars \u00b7 {format_elapsed(elapsed)}"
            self.update("")


# ---------------------------------------------------------------------------
# Slash command definitions and hint bar
# ---------------------------------------------------------------------------

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "show this help"),
    ("/h", "show this help (shortcut)"),
    ("/mute <member>", "exclude member from broadcast"),
    ("/mute", "show currently muted members"),
    ("/unmute <member>", "re-include member in broadcast"),
    ("/writable", "toggle writable mode (allow/deny file edits)"),
    ("/quit", "quit kd chat"),
    ("/exit", "quit kd chat"),
]


def match_commands(prefix: str) -> list[tuple[str, str]]:
    """Return slash commands whose name starts with the given prefix.

    The prefix is compared against the command word (the part before any
    space / argument placeholder).  An empty prefix or bare "/" returns all
    commands.
    """
    prefix = prefix.lower()
    matches = []
    for cmd, desc in SLASH_COMMANDS:
        cmd_word = cmd.split()[0]
        if cmd_word.startswith(prefix):
            matches.append((cmd, desc))
    return matches


class CommandHintBar(Static):
    """A hint bar that shows matching slash commands above the input area.

    Hidden by default. Call show_hints() with a prefix to display
    matching commands, or hide_hints() to remove it.
    """

    DEFAULT_CSS = """
    CommandHintBar {
        dock: bottom;
        height: auto;
        max-height: 6;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        display: none;
    }
    CommandHintBar.visible {
        display: block;
    }
    """

    def show_hints(self, prefix: str) -> None:
        """Show commands matching prefix. Hides if none match."""
        matches = match_commands(prefix)
        if not matches:
            self.hide_hints()
            return
        lines = [f"  {cmd}  {desc}" for cmd, desc in matches]
        self.update("\n".join(lines))
        self.add_class("visible")

    def hide_hints(self) -> None:
        """Hide the hint bar."""
        self.remove_class("visible")
        self.update("")

    def first_match(self, prefix: str) -> str | None:
        """Return the command word of the first matching command, or None."""
        matches = match_commands(prefix)
        if not matches:
            return None
        return matches[0][0].split()[0]
