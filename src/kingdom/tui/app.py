"""ChatApp — main Textual application for kd council chat."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter, deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

from textual.app import App, ComposeResult, ScreenStackError
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.css.query import QueryError
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static, TextArea

from kingdom.agent import resolve_all_agents
from kingdom.config import load_config
from kingdom.council import Council
from kingdom.state import read_json, write_json
from kingdom.thread import (
    add_message,
    format_thread_history,
    get_thread,
    is_error_response,
    is_interrupted_response,
    is_timeout_response,
    list_messages,
    thread_dir,
)

from .poll import NewMessage, StreamDelta, StreamFinished, StreamStarted, ThinkingDelta, ThreadPoller, ToolUseEvent
from .widgets import (
    CommandHintBar,
    ErrorPanel,
    MessagePanel,
    StreamingPanel,
    ThinkingPanel,
    WaitingPanel,
    format_reply_text,
)

logger = logging.getLogger(__name__)

MENTION_RE = re.compile(r"(?<!\w)@(\w+)")
PENDING_MESSAGES_FILENAME = ".pending-messages.json"


@dataclass(frozen=True)
class QueuedDelivery:
    """A King message waiting for its turn to reach the council."""

    delivery_id: str
    body: str
    targets: tuple[str, ...]
    to: str
    completed_targets: tuple[str, ...] = ()
    first_exchange: bool | None = None


def load_pending_deliveries(tdir: Path) -> deque[QueuedDelivery]:
    path = tdir / PENDING_MESSAGES_FILENAME
    if not path.exists():
        return deque()

    data = read_json(path)
    return deque(
        QueuedDelivery(
            delivery_id=str(item["id"]),
            body=str(item["body"]),
            targets=tuple(str(target) for target in item["targets"]),
            to=str(item["to"]),
            completed_targets=tuple(str(target) for target in item.get("completed_targets", [])),
            first_exchange=item.get("first_exchange"),
        )
        for item in data.get("deliveries", [])
    )


def write_pending_deliveries(tdir: Path, deliveries: deque[QueuedDelivery]) -> None:
    path = tdir / PENDING_MESSAGES_FILENAME
    if not deliveries:
        path.unlink(missing_ok=True)
        return

    write_json(
        path,
        {
            "deliveries": [
                {
                    "id": delivery.delivery_id,
                    "body": delivery.body,
                    "targets": list(delivery.targets),
                    "to": delivery.to,
                    "completed_targets": list(delivery.completed_targets),
                    "first_exchange": delivery.first_exchange,
                }
                for delivery in deliveries
            ]
        },
    )


def mention_bump(response_text: str, remaining: list[str], valid_members: list[str]) -> list[str]:
    """Reorder remaining queue by bumping @mentioned members to the front.

    Mentioned valid members (that are in *remaining*) move to the front in
    mention order.  Non-mentioned members keep their relative order.
    @king and unknown names are ignored.  Duplicates are deduplicated.
    """
    mentions = MENTION_RE.findall(response_text)
    valid_set = set(valid_members)
    remaining_set = set(remaining)

    # Collect mentioned names that are valid members in the remaining queue
    bumped: list[str] = []
    seen: set[str] = set()
    for name in mentions:
        if name in valid_set and name in remaining_set and name not in seen and name != "king":
            bumped.append(name)
            seen.add(name)

    if not bumped:
        return remaining

    # Rest keeps relative order
    rest = [n for n in remaining if n not in seen]
    return bumped + rest


CHAT_PREAMBLE = (
    "[MODE: READ-ONLY] You do not have file-write permissions in this session.\n"
    "You are {name}, participating in a group discussion with other AI agents and the King (human). "
    "This is a live conversation — read the full thread before responding. "
    "Reference specific points others have made (agree, disagree, extend, or synthesize). "
    "Don't just answer the King's question in isolation — engage with what's already been said. "
    "If you disagree with another agent, say so directly and explain why. "
    "Do NOT create, edit, or write files. Do NOT run git commands that modify state. "
    "If asked to edit or create files, state that you are in read-only mode and cannot comply.\n\n"
)

WRITABLE_CHAT_PREAMBLE = (
    "[MODE: WRITABLE] You have full file-write permissions in this session.\n"
    "You are {name}, participating in a group discussion with other AI agents and the King (human). "
    "This is a live conversation — read the full thread before responding. "
    "Reference specific points others have made (agree, disagree, extend, or synthesize). "
    "Don't just answer the King's question in isolation — engage with what's already been said. "
    "If you disagree with another agent, say so directly and explain why. "
    "You have full permissions — you may edit files, create tickets, run git commands, "
    "and execute any action the King requests. Act on instructions directly.\n\n"
)


def format_timestamp(ts: datetime) -> str:
    """Format a datetime as a short timestamp for display in message panels.

    Returns 'HH:MM' for today, 'Mon HH:MM' for other days.
    """
    now = datetime.now(UTC)
    local_ts = ts.astimezone()
    local_now = now.astimezone()
    if local_ts.date() == local_now.date():
        return local_ts.strftime("%H:%M")
    return local_ts.strftime("%a %H:%M")


def build_branch_context(base: Path, branch: str) -> str:
    """Build a context block with the current branch name and ticket summary.

    Returns a string like::

        [Branch context]
        Branch: feature/my-feature
        Tickets:
          e0eb  in_progress  P2  kd chat: inject branch context
          a1b2  open         P1  Fix parsing bug
        Contexts (concurrent agent sessions):
          codex:abc123  codex/agent  e0eb

    Returns an empty string if no branch info is available.
    """
    from kingdom.state import branch_root, compact_context_id, list_execution_contexts
    from kingdom.ticket import list_tickets

    lines = ["[Branch context]", f"Branch: {branch}"]

    tickets_dir = branch_root(base, branch) / "tickets"
    tickets = [t for t in list_tickets(tickets_dir) if t.status != "closed"]
    if tickets:
        lines.append("Tickets:")
        for t in tickets:
            status = t.status.replace("_", " ")
            lines.append(f"  {t.id}  {status:12s}  P{t.priority}  {t.title}")

    contexts = [context for context in list_execution_contexts(base, feature=branch) if context.get("ticket_id")]
    if contexts:
        lines.append("Contexts (concurrent agent sessions):")
        for context in contexts:
            states = []
            if context["stale"]:
                states.append("stale")
            if not context["active"]:
                states.append("completed")
            state = f" ({', '.join(states)})" if states else ""
            agent_type = f"/{context['agent_type']}" if context.get("agent_type") else ""
            parent = context.get("parent_agent_id")
            parent_label = f" child-of:{compact_context_id(parent)}" if isinstance(parent, str) else ""
            lines.append(
                f"  {compact_context_id(context['context_id'])}  "
                f"{context['host']}/{context['role']}{agent_type}{state}{parent_label}  {context['ticket_id']}"
            )

    return "\n".join(lines) + "\n\n"


class MessageLog(VerticalScroll):
    """Scrollable container for chat messages.

    Wraps Textual's VerticalScroll with smart auto-scroll: new content only
    scrolls to bottom when the user is already near the bottom.  If the user
    has scrolled up to read history, the view stays put.

    ``is_following`` — True when auto-scroll is active (user is near bottom).
    ``SCROLL_THRESHOLD`` — pixel distance from bottom that counts as "near".

    Call ``scroll_if_following()`` **before** mounting or updating content so
    that ``is_following`` reflects the user's position *before* the layout
    shifts.  The actual ``scroll_end`` runs after the next refresh (when the
    new layout has been computed).  Multiple calls coalesce into one scroll
    per frame via a ``_scroll_pending`` flag.
    """

    SCROLL_THRESHOLD: int = 5

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._scroll_pending: bool = False

    @property
    def is_following(self) -> bool:
        """True when the viewport is at or near the bottom.

        Uses a position-based check rather than Textual's internal anchor
        state.  Returns True when ``scroll_y`` is within ``SCROLL_THRESHOLD``
        pixels of ``max_scroll_y``, or when there is nothing to scroll.
        """
        if self.max_scroll_y == 0:
            return True
        return self.scroll_y >= self.max_scroll_y - self.SCROLL_THRESHOLD

    def scroll_if_following(self) -> None:
        """Capture follow intent and schedule a single deferred scroll.

        Call **before** mounting or updating content so that ``is_following``
        reflects the user's position before the layout shifts.  The actual
        ``scroll_end`` runs after the next refresh (new layout computed).
        Multiple calls coalesce into one scroll per frame.
        """
        if self.is_following and not self._scroll_pending:
            self._scroll_pending = True
            self.call_after_refresh(self.do_deferred_scroll)

    def do_deferred_scroll(self) -> None:
        """Execute the deferred scroll-to-bottom."""
        self._scroll_pending = False
        self.scroll_end(animate=False)


class StatusBar(Static):
    """Keybinding hints at the bottom."""


class InputArea(TextArea):
    """User input area at the bottom of the screen.

    Enter sends the message (posts Submit to the app).
    Shift+Enter inserts a newline.
    Tab after @partial completes member names.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("alt+left", "cursor_word_left", "Cursor word left", show=False),
        Binding("alt+right", "cursor_word_right", "Cursor word right", show=False),
        Binding("alt+shift+left", "cursor_word_left(True)", "Cursor word left select", show=False),
        Binding("alt+shift+right", "cursor_word_right(True)", "Cursor word right select", show=False),
    ]

    class Submit(Message):
        """Posted when the user presses Enter to send."""

    def __init__(self, member_names: list[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.member_names: list[str] = member_names or []
        # Tab-completion state: tracks cycling through multiple matches
        self.tab_candidates: list[str] = []
        self.tab_index: int = 0
        self.tab_prefix_start: tuple[int, int] = (0, 0)  # (row, col) of "@"
        self.tab_prefix: str = ""  # the partial text after "@" that triggered completion

    async def handle_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submit())
            return
        if event.key == "shift+enter":
            # Insert a literal newline instead of submitting.
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self.handle_tab_complete()
            return
        # Any non-tab key resets completion state
        self.tab_candidates = []
        self.tab_index = 0
        await super()._on_key(event)

    _on_key = handle_key

    def handle_tab_complete(self) -> None:
        """Complete @mention or /command at cursor position, cycling on repeated Tab."""
        from .widgets import match_commands

        if self.tab_candidates:
            # Cycling: replace the previously inserted completion with the next one
            self.tab_index = (self.tab_index + 1) % len(self.tab_candidates)
            candidate = self.tab_candidates[self.tab_index]
            row, col = self.cursor_location
            start = self.tab_prefix_start
            if self.tab_prefix.startswith("/"):
                self.replace(f"{candidate} ", start, (row, col), maintain_selection_offset=False)
            else:
                self.replace(f"@{candidate} ", start, (row, col), maintain_selection_offset=False)
            return

        # First Tab press: determine if completing a slash command or @mention
        row, col = self.cursor_location
        line = self.document.get_line(row)
        text_before_cursor = line[:col]

        # Slash command completion (first line, starts with /, no spaces yet)
        if row == 0 and text_before_cursor.startswith("/") and " " not in text_before_cursor:
            matches = match_commands(text_before_cursor)
            if matches:
                # Deduplicate command words while preserving order
                seen: set[str] = set()
                candidates: list[str] = []
                for cmd, _desc in matches:
                    word = cmd.split()[0]
                    if word not in seen:
                        seen.add(word)
                        candidates.append(word)
                self.tab_candidates = candidates
                self.tab_index = 0
                self.tab_prefix_start = (0, 0)
                self.tab_prefix = text_before_cursor
                self.replace(f"{candidates[0]} ", (0, 0), (row, col), maintain_selection_offset=False)
            return

        # @mention completion
        match = re.search(r"@(\w*)$", text_before_cursor)
        if not match:
            return

        prefix = match.group(1).lower()
        at_col = match.start()

        # "all" is a valid completion target
        completable = [*self.member_names, "all"]
        if prefix:
            candidates = [name for name in completable if name.lower().startswith(prefix)]
        else:
            candidates = list(completable)

        if not candidates:
            return

        self.tab_candidates = candidates
        self.tab_index = 0
        self.tab_prefix_start = (row, at_col)
        self.tab_prefix = prefix

        candidate = candidates[0]
        end = (row, col)
        start = (row, at_col)
        self.replace(f"@{candidate} ", start, end, maintain_selection_offset=False)


class ChatScreen(Screen):
    """Non-scrollable screen so only MessageLog scrolls.

    Textual's default Screen has ``overflow-y: auto`` in its ``DEFAULT_CSS``,
    making it a scroll container.  Previous attempts to override via
    ``ChatApp.CSS`` or inline styles lost the CSS specificity battle against
    ``Screen.DEFAULT_CSS``.

    Setting ``DEFAULT_CSS`` on the *subclass* with the ``ChatScreen`` selector
    wins specificity over the base ``Screen`` rule.  The
    ``allow_vertical_scroll`` overrides are belt-and-suspenders — they block
    keyboard/mouse scroll actions even if CSS somehow slips.
    """

    @property
    def allow_vertical_scroll(self) -> bool:
        return False

    @property
    def allow_horizontal_scroll(self) -> bool:
        return False


class ChatApp(App):
    """Council chat TUI."""

    TITLE = "kd council chat"
    CSS_PATH = "chat.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "interrupt", "Interrupt/Quit"),
        ("end", "scroll_bottom", "Jump to bottom"),
        ("ctrl+t", "toggle_thinking", "Toggle thinking"),
    ]

    THINKING_CYCLE: ClassVar[list[str]] = ["auto", "show", "hide"]

    def get_default_screen(self) -> ChatScreen:
        return ChatScreen(id="_default")

    def __init__(
        self,
        base: Path,
        branch: str,
        thread_id: str,
        debug_streams: bool = False,
        writable: bool = False,
        ansi_color: bool = False,
    ) -> None:
        super().__init__(ansi_color=ansi_color)
        self.base = base
        self.branch = branch
        self.thread_id = thread_id
        self.debug_streams = debug_streams
        self.writable = writable
        self.poller: ThreadPoller | None = None
        self.member_names: list[str] = []
        self.council: Council | None = None
        self.interrupted = False
        self.muted: set[str] = set()
        self.generation: int = 0
        self.thinking_visibility: str = "auto"
        self.chat_mode: str = "natural"
        self.auto_rounds: int = 1
        self.reply_target: str | None = None
        self.delivery_queue: deque[QueuedDelivery] = deque()
        self.delivery_active = False
        self.active_delivery_id: str | None = None
        self.completed_delivery_targets: Counter[str] = Counter()
        self.seen_delivery_targets: Counter[str] = Counter()
        self.rendered_message_sequences: set[int] = set()

    def compose(self) -> ComposeResult:
        # Load thread metadata for header
        try:
            meta = get_thread(self.base, self.branch, self.thread_id)
            self.member_names = [m for m in meta.members if m != "king"]
        except FileNotFoundError:
            self.member_names = []

        members_str = " ".join(self.member_names) if self.member_names else "no members"
        yield Static(
            f"kd council chat · {self.thread_id} · {members_str}",
            id="header-bar",
        )
        yield MessageLog(id="message-log")
        yield StatusBar("Esc: interrupt/quit · Enter: send · Tab: @complete · Ctrl+T: thinking")
        yield CommandHintBar(id="command-hints")
        yield InputArea(member_names=self.member_names, id="input-area")

    def on_mount(self) -> None:
        """Initialize poller, council, and start polling."""

        tdir = thread_dir(self.base, self.branch, self.thread_id)

        # Clean up stale stream files from previous sessions so the poller
        # doesn't replay them as ghost streams.
        for stale in tdir.glob(".stream-*.jsonl"):
            stale.unlink()

        # Load config for backends, thinking visibility, and chat settings
        cfg = load_config(self.base)
        self.thinking_visibility = cfg.council.thinking_visibility
        self.chat_mode = cfg.council.chat.mode
        self.auto_rounds = cfg.council.chat.auto_rounds
        agent_configs = resolve_all_agents(cfg.agents)
        member_backends = {}
        for name in self.member_names:
            ac = agent_configs.get(name)
            if ac:
                member_backends[name] = ac.backend

        self.poller = ThreadPoller(
            thread_dir=tdir,
            member_backends=member_backends,
        )

        # Create Council for direct query dispatch.  Chat is stateless: no
        # load_sessions, no base/branch on members (prevents PID writes to
        # shared session files).  Context comes from thread history injection.
        self.council = Council.create(base=self.base)
        branch_context = build_branch_context(self.base, self.branch)
        preamble_template = WRITABLE_CHAT_PREAMBLE if self.writable else CHAT_PREAMBLE
        for member in self.council.members:
            member.preamble = preamble_template.format(name=member.name) + branch_context
            if self.writable:
                member.writable = True

        # Load existing messages from thread history
        self.load_history()
        self.restore_pending_deliveries(tdir)

        self.set_interval(0.1, self.poll_updates)

        if self.delivery_queue:
            self.delivery_active = True
            self.run_worker(self.drain_delivery_queue(), exclusive=False)

        # Focus the input area
        input_area = self.query_one("#input-area", TextArea)
        input_area.focus()

    def action_scroll_bottom(self) -> None:
        """Jump to bottom (auto-follow re-engages via position check)."""
        log = self.query_one("#message-log", MessageLog)
        log.scroll_end(animate=False)
        self.update_status_bar(log)

    def action_toggle_thinking(self) -> None:
        """Cycle thinking visibility: auto -> show -> hide -> auto.

        Updates all existing ThinkingPanel widgets to match the new mode.
        """
        cycle = self.THINKING_CYCLE
        idx = cycle.index(self.thinking_visibility) if self.thinking_visibility in cycle else 0
        self.thinking_visibility = cycle[(idx + 1) % len(cycle)]

        # Apply the new mode to all existing ThinkingPanel widgets
        self.apply_thinking_visibility()

        labels = {"auto": "auto (collapse on answer)", "show": "always show", "hide": "hidden"}
        label = labels.get(self.thinking_visibility, self.thinking_visibility)
        self.show_system_message(f"Thinking: {label}")

    def apply_thinking_visibility(self) -> None:
        """Apply the current thinking_visibility to all existing ThinkingPanel widgets."""
        panels = self.query(ThinkingPanel)
        for panel in panels:
            if self.thinking_visibility == "hide":
                panel.display = False
            elif self.thinking_visibility == "show":
                panel.display = True
                if not panel.user_pinned:
                    panel.expanded = True
                    panel.remove_class("collapsed")
                    panel.update_display()
            else:
                # auto: make visible, but respect existing collapsed/expanded state
                panel.display = True

    def update_status_bar(self, log: MessageLog | None = None) -> None:
        """Update status bar to show scroll state."""
        if log is None:
            log = self.query_one("#message-log", MessageLog)
        bar = self.query_one(StatusBar)
        if not log.is_following:
            bar.update("Esc: interrupt/quit · Enter: send · End: jump to bottom · Ctrl+T: thinking")
        else:
            bar.update("Esc: interrupt/quit · Enter: send · Ctrl+T: thinking")

    def action_interrupt(self) -> None:
        """Handle Escape: clear input, interrupt queries, or quit.

        1. Input has text → clear it, return
        2. Active queries running → interrupt them
        3. Already interrupted / nothing running → exit app
        """
        # If the input area has text, clear it first
        try:
            input_area = self.query_one("#input-area", InputArea)
            if input_area.text.strip():
                input_area.clear()
                return
        except (QueryError, ScreenStackError):
            logger.debug("Could not query input area during interrupt", exc_info=True)

        if not self.council:
            self.exit()
            return

        # Second Escape after interrupt: force quit
        if self.interrupted:
            self.exit()
            return

        # Check for active queries
        active = [m for m in self.council.members if m.process is not None]
        if not active:
            self.exit()
            return

        # Kill active processes
        self.interrupted = True
        for member in active:
            if member.process:
                member.process.terminate()

        # Replace waiting/streaming panels with interrupted indicators immediately
        log = self.query_one("#message-log", MessageLog)
        for member in active:
            replaced = False
            for prefix in ("wait", "stream", "thinking"):
                panel_id = f"{prefix}-{member.name}"
                try:
                    panel = log.query_one(f"#{panel_id}")
                    if not replaced:
                        error_panel = ErrorPanel(
                            sender=member.name,
                            error="*Interrupted*",
                            id=f"interrupted-{member.name}",
                        )
                        log.mount(error_panel, before=panel)
                        replaced = True
                    panel.remove()
                except QueryError:
                    pass

    def load_history(self) -> None:
        """Load existing messages and render them in the message log."""
        try:
            messages = list_messages(self.base, self.branch, self.thread_id)
        except FileNotFoundError:
            return

        if not messages:
            return

        log = self.query_one("#message-log", MessageLog)

        for msg in messages:
            # Prefer msg.status metadata; fall back to body-prefix sniffing for legacy messages
            has_error = (
                msg.status in ("error", "timeout", "interrupted")
                if msg.status
                else (is_error_response(msg.body) or is_interrupted_response(msg.body))
            )
            if msg.from_ != "king" and has_error:
                timed_out = msg.status == "timeout" if msg.status else is_timeout_response(msg.body)
                panel = ErrorPanel(
                    sender=msg.from_,
                    error=msg.body,
                    timed_out=timed_out,
                    id=f"msg-{msg.sequence}",
                )
            else:
                panel = MessagePanel(
                    sender=msg.from_,
                    body=msg.body,
                    member_names=self.member_names,
                    timestamp=format_timestamp(msg.timestamp),
                    id=f"msg-{msg.sequence}",
                )
            log.mount(panel)

        # Update poller so it doesn't re-report these messages
        if self.poller and messages:
            self.poller.last_sequence = messages[-1].sequence

        log.scroll_end(animate=False)

    def on_input_area_submit(self, _: InputArea.Submit) -> None:
        """Handle submit events from the input widget."""
        self.send_message()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Show/hide slash command hints as the user types."""
        hint_bar = self.query_one("#command-hints", CommandHintBar)
        text = event.text_area.text
        # Only the first line matters for slash command detection
        first_line = text.split("\n", 1)[0]

        if first_line.startswith("/") and " " not in first_line:
            # User is typing a slash command prefix — show matching hints
            hint_bar.show_hints(first_line)
        else:
            hint_bar.hide_hints()

    def on_message_panel_reply(self, event: MessagePanel.Reply) -> None:
        """Toggle reply target: click sets, same click clears, different click switches."""
        input_area = self.query_one("#input-area", InputArea)

        if self.reply_target == event.sender:
            # Toggle off: clear reply target
            self.clear_reply_target(input_area)
        else:
            # Set or switch reply target
            old_target = self.reply_target
            self.reply_target = event.sender

            # Remove old @mention if switching targets
            if old_target:
                old_prefix = format_reply_text(old_target)
                text = input_area.text
                if text.startswith(old_prefix):
                    text = text[len(old_prefix) :]
                    input_area.load_text(text)

            # Prefill with new @mention
            reply_text = format_reply_text(event.sender)
            existing = input_area.text
            if not existing.startswith(reply_text):
                if existing.strip():
                    input_area.load_text(reply_text + existing)
                else:
                    input_area.load_text(reply_text)

            input_area.focus()
            input_area.move_cursor_relative(columns=len(reply_text))

            # Update panel visuals
            self.update_reply_panel_visuals()

    def clear_reply_target(self, input_area: TextArea | None = None) -> None:
        """Clear the active reply target and clean up input."""
        if not self.reply_target:
            return
        old_prefix = format_reply_text(self.reply_target)
        self.reply_target = None
        if input_area is None:
            input_area = self.query_one("#input-area", InputArea)
        text = input_area.text
        if text.startswith(old_prefix):
            remaining = text[len(old_prefix) :]
            input_area.load_text(remaining)
        self.update_reply_panel_visuals()

    def update_reply_panel_visuals(self) -> None:
        """Update border subtitles on message panels to reflect reply state."""
        try:
            log = self.query_one("#message-log", MessageLog)
        except QueryError:
            return
        for panel in log.query(MessagePanel):
            if panel.sender == "king":
                continue
            if self.reply_target and panel.sender == self.reply_target:
                panel.border_subtitle = "replying \u2022 click to cancel"
            else:
                panel.border_subtitle = "click: reply \u00b7 shift: copy"

    def send_message(self) -> None:
        """Send the current input as a king message or handle slash command."""
        input_area = self.query_one("#input-area", TextArea)
        text = input_area.text.strip()
        if not text:
            return

        input_area.clear()

        # Clear reply target after sending
        self.reply_target = None
        self.update_reply_panel_visuals()

        # Handle slash commands
        if text.startswith("/"):
            self.handle_slash_command(text)
            return

        # Manual mode: require explicit @mention
        mentions = re.findall(r"(?<!\w)@(\w+)", text)
        if self.chat_mode == "manual" and not mentions:
            self.notify("Use @member to direct your message (e.g. @claude). Try @all for everyone.", severity="warning")
            # Put the text back so user can add @mention
            input_area.load_text(text)
            return

        # Parse @mentions
        targets = self.parse_targets(text)

        to = targets[0] if len(targets) == 1 else "all"
        delivery = QueuedDelivery(
            delivery_id=uuid4().hex,
            body=text,
            targets=tuple(targets),
            to=to,
        )
        queued = self.delivery_active
        self.delivery_queue.append(delivery)
        write_pending_deliveries(thread_dir(self.base, self.branch, self.thread_id), self.delivery_queue)

        self.render_king_message(delivery)

        if queued:
            self.notify(f"Message queued ({len(self.delivery_queue)} waiting)")
            return

        self.delivery_active = True
        self.run_worker(self.drain_delivery_queue(), exclusive=False)

    def render_king_message(self, delivery: QueuedDelivery) -> None:
        """Render a submitted message before its council delivery begins."""
        log = self.query_one("#message-log", MessageLog)
        log.scroll_if_following()  # capture intent BEFORE mounts
        king_panel = MessagePanel(
            sender="king",
            body=delivery.body,
            member_names=self.member_names,
            id=f"king-{delivery.delivery_id}",
        )
        log.mount(king_panel)

    def restore_pending_deliveries(self, tdir: Path) -> None:
        """Load deliveries whose Council dispatch did not finish."""
        pending = load_pending_deliveries(tdir)
        persisted_ids = {message.delivery_id for message in list_messages(self.base, self.branch, self.thread_id)}
        self.delivery_queue = pending
        for delivery in self.delivery_queue:
            if delivery.delivery_id not in persisted_ids:
                self.render_king_message(delivery)

    async def drain_delivery_queue(self) -> None:
        """Deliver submitted messages one at a time in FIFO order."""
        try:
            while self.delivery_queue:
                delivery = self.delivery_queue[0]
                self.interrupted = False
                self.generation += 1
                await self.deliver_message(delivery, self.generation)
                self.delivery_queue.popleft()
                write_pending_deliveries(thread_dir(self.base, self.branch, self.thread_id), self.delivery_queue)
                self.poll_updates()
        finally:
            self.delivery_active = False

    async def deliver_message(self, delivery: QueuedDelivery, generation: int) -> None:
        """Persist and dispatch one queued king message."""
        prior_messages = list_messages(self.base, self.branch, self.thread_id)
        message = next((item for item in prior_messages if item.delivery_id == delivery.delivery_id), None)
        if message is None:
            message = add_message(
                self.base,
                self.branch,
                self.thread_id,
                from_="king",
                to=delivery.to,
                body=delivery.body,
                delivery_id=delivery.delivery_id,
            )
            prior_messages.append(message)
        self.rendered_message_sequences.add(message.sequence)

        is_first_exchange = delivery.first_exchange
        if is_first_exchange is None:
            is_first_exchange = not any(item.from_ != "king" for item in prior_messages)
            delivery = replace(delivery, first_exchange=is_first_exchange)
            self.delivery_queue[0] = delivery
            write_pending_deliveries(thread_dir(self.base, self.branch, self.thread_id), self.delivery_queue)

        persisted_targets = Counter(
            item.from_ for item in prior_messages if item.delivery_id == delivery.delivery_id and item.from_ != "king"
        )
        recovered_targets = persisted_targets - Counter(delivery.completed_targets)
        if recovered_targets:
            delivery = replace(
                delivery,
                completed_targets=(*delivery.completed_targets, *recovered_targets.elements()),
            )
            self.delivery_queue[0] = delivery
            write_pending_deliveries(thread_dir(self.base, self.branch, self.thread_id), self.delivery_queue)

        self.active_delivery_id = delivery.delivery_id
        self.completed_delivery_targets = Counter(delivery.completed_targets)
        self.seen_delivery_targets = Counter()

        try:
            await self.dispatch_delivery(delivery, generation, is_first_exchange)
        finally:
            self.active_delivery_id = None
            self.completed_delivery_targets.clear()
            self.seen_delivery_targets.clear()

    async def dispatch_delivery(
        self,
        delivery: QueuedDelivery,
        generation: int,
        is_first_exchange: bool,
    ) -> None:
        """Run the persisted delivery schedule, skipping completed occurrences."""

        targets = list(delivery.targets)
        tdir = thread_dir(self.base, self.branch, self.thread_id)
        log = self.query_one("#message-log", MessageLog)
        for name in targets:
            if self.delivery_target_pending(name):
                await self.await_remove_member_panels(log, name)

        if delivery.to == "all":
            sequential = self.chat_mode in ("round_robin", "manual")
            panel_targets = targets[:1] if sequential else targets
            for name in panel_targets:
                if self.delivery_target_pending(name) and not log.query(f"#wait-{name}"):
                    log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
            await self.run_chat_round(targets, generation, tdir, is_first_exchange)
            return

        name = targets[0]
        if not self.claim_delivery_target(name):
            return
        if not log.query(f"#wait-{name}"):
            log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
        member = self.council.get_member(name) if self.council else None
        if member:
            stream_path = tdir / f".stream-{name}.jsonl"
            await self.run_query(member, stream_path, generation=generation)

    def delivery_target_pending(self, name: str) -> bool:
        """Return whether the next planned query for a member is unfinished."""
        if self.active_delivery_id is None:
            return True
        return self.seen_delivery_targets[name] + 1 > self.completed_delivery_targets[name]

    def claim_delivery_target(self, name: str) -> bool:
        """Record a planned query occurrence and return whether it must run."""
        if self.active_delivery_id is None:
            return True
        self.seen_delivery_targets[name] += 1
        return self.seen_delivery_targets[name] > self.completed_delivery_targets[name]

    def complete_delivery_target(self, name: str) -> None:
        """Persist completion of one member query in the active delivery."""
        if self.active_delivery_id is None:
            return
        for index, delivery in enumerate(self.delivery_queue):
            if delivery.delivery_id != self.active_delivery_id:
                continue
            self.delivery_queue[index] = replace(
                delivery,
                completed_targets=(*delivery.completed_targets, name),
            )
            self.completed_delivery_targets[name] += 1
            write_pending_deliveries(thread_dir(self.base, self.branch, self.thread_id), self.delivery_queue)
            return

    async def run_query(self, member, stream_path: Path, generation: int | None = None) -> str | None:
        """Run a member query with full thread context, then persist and clean up.

        When *generation* is passed, the response is discarded if ``self.generation``
        has moved on and superseded this delivery.

        Returns the response body text, or None if discarded/errored.
        """
        body = None
        persisted = False
        try:
            timeout = self.council.timeout if self.council else 600
            tdir = thread_dir(self.base, self.branch, self.thread_id)
            prompt_with_history = format_thread_history(tdir, member.name)
            response = await asyncio.to_thread(member.query, prompt_with_history, timeout, stream_path, max_retries=0)

            # Discard stale results when the user has already sent a new message.
            if generation is not None and self.generation != generation:
                logger.debug(
                    "Discarding stale response from %s (gen %d != %d)", member.name, generation, self.generation
                )
                return None

            # Use cleaner message for interrupted queries with no useful text
            if self.interrupted and not response.text:
                body = "*Interrupted*"
            elif self.interrupted and response.text:
                body = response.thread_body() + "\n\n*[Interrupted — response may be incomplete]*"
            else:
                body = response.thread_body()

            # Always persist response to thread files (source of truth)
            add_message(
                self.base,
                self.branch,
                self.thread_id,
                from_=member.name,
                to="king",
                body=body,
                delivery_id=self.active_delivery_id,
                **response.thread_metadata(),
            )
            persisted = True

        except (OSError, RuntimeError, ValueError) as exc:
            # Persist the exception as an error message
            logger.exception("Member query failed for %s", member.name)
            error_body = f"*Error: {exc}*"
            add_message(
                self.base,
                self.branch,
                self.thread_id,
                from_=member.name,
                to="king",
                body=error_body,
                delivery_id=self.active_delivery_id,
            )
            persisted = True
        finally:
            if persisted:
                self.complete_delivery_target(member.name)

            # Chat is stateless — clear session_id so the next query doesn't
            # pass --resume to the agent.  Thread history injection provides
            # full context; accumulating session_id causes cross-talk (0f27).
            member.session_id = None

            # Optionally preserve raw stream events for debugging.
            if stream_path.exists() and self.debug_streams:
                debug_path = self.build_debug_stream_path(stream_path, member.name)
                stream_path.replace(debug_path)

            # Stream file is NOT deleted here — the poller needs to drain final
            # events (thinking tokens, last text deltas) before cleanup.  Stale
            # files are cleaned up on next session launch (on_mount).
        return body

    def build_debug_stream_path(self, stream_path: Path, member_name: str) -> Path:
        """Build a unique path for preserved stream debug artifacts."""
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return stream_path.parent / f".debug-stream-{member_name}-{timestamp}.jsonl"

    async def run_chat_round(self, targets: list[str], generation: int, tdir: Path, is_first_exchange: bool) -> None:
        """Coordinate a chat round after the king sends a message.

        Dispatches to mode-specific logic:
        - natural: parallel broadcast first, then shuffled round-robin auto-turns
        - round_robin: fixed-order sequential turns for auto_rounds rounds
        - manual: only @mentioned targets, no auto-turns
        - broadcast: parallel to all, auto_rounds additional parallel rounds
        """
        if not self.council:
            return

        mode = self.chat_mode

        if mode == "manual":
            await self.run_mode_manual(targets, generation, tdir)
        elif mode == "broadcast":
            await self.run_mode_broadcast(targets, generation, tdir, is_first_exchange)
        elif mode == "round_robin":
            await self.run_mode_round_robin(targets, generation, tdir)
        else:
            # natural (default)
            await self.run_mode_natural(targets, generation, tdir, is_first_exchange)

    async def run_mode_natural(self, targets: list[str], generation: int, tdir: Path, is_first_exchange: bool) -> None:
        """Natural mode: parallel broadcast first turn, then shuffled round-robin."""
        if is_first_exchange:
            # First exchange: parallel broadcast, no auto-turns
            await self.parallel_query(targets, generation, tdir)
            return

        # Follow-up: shuffled sequential only — each member responds once
        await self.sequential_auto_turns(targets, generation, tdir, shuffle=True)

    async def run_mode_round_robin(self, targets: list[str], generation: int, tdir: Path) -> None:
        """Round-robin mode: no initial broadcast, fixed-order sequential turns."""
        # First turn: sequential through targets, mounting WaitingPanel per-agent
        for name in targets:
            if self.interrupted or self.generation != generation:
                return
            if not self.claim_delivery_target(name):
                continue
            member = self.council.get_member(name)
            if not member:
                continue
            log = self.query_one("#message-log", MessageLog)
            log.scroll_if_following()
            await self.await_remove_member_panels(log, name)
            if not log.query(f"#wait-{name}"):
                log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
            stream_path = tdir / f".stream-{name}.jsonl"
            await self.run_query(member, stream_path, generation=generation)

        # Auto-turns: fixed-order sequential
        await self.sequential_auto_turns(targets, generation, tdir, shuffle=False)

    async def run_mode_manual(self, targets: list[str], generation: int, tdir: Path) -> None:
        """Manual mode: only query @mentioned targets, no auto-turns."""
        # Sequential through mentioned targets, mounting WaitingPanel per-agent
        for name in targets:
            if self.interrupted or self.generation != generation:
                return
            if not self.claim_delivery_target(name):
                continue
            member = self.council.get_member(name)
            if not member:
                continue
            log = self.query_one("#message-log", MessageLog)
            log.scroll_if_following()
            await self.await_remove_member_panels(log, name)
            if not log.query(f"#wait-{name}"):
                log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
            stream_path = tdir / f".stream-{name}.jsonl"
            await self.run_query(member, stream_path, generation=generation)

    async def run_mode_broadcast(
        self, targets: list[str], generation: int, tdir: Path, is_first_exchange: bool
    ) -> None:
        """Broadcast mode: parallel to all each turn, auto_rounds additional rounds."""
        # First turn: parallel (WaitingPanels mounted by send_message)
        await self.parallel_query(targets, generation, tdir)
        if self.generation != generation:
            return

        # First exchange: no auto-rounds
        if is_first_exchange:
            return

        # Additional broadcast rounds
        if self.auto_rounds <= 0:
            return
        for _round in range(self.auto_rounds):
            if self.interrupted or self.generation != generation:
                return
            log = self.query_one("#message-log", MessageLog)
            log.scroll_if_following()
            for name in targets:
                if not self.delivery_target_pending(name):
                    continue
                await self.await_remove_member_panels(log, name)
                if not log.query(f"#wait-{name}"):
                    log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
            await self.parallel_query(targets, generation, tdir)
            if self.generation != generation:
                return

    async def parallel_query(self, targets: list[str], generation: int, tdir: Path) -> None:
        """Run queries for all targets in parallel."""
        coros = []
        for name in targets:
            if not self.claim_delivery_target(name):
                continue
            member = self.council.get_member(name)
            if member:
                stream_path = tdir / f".stream-{name}.jsonl"
                coros.append(self.run_query(member, stream_path, generation=generation))
        if coros:
            await asyncio.gather(*coros)

    async def sequential_auto_turns(
        self,
        targets: list[str],
        generation: int,
        tdir: Path,
        shuffle: bool,
    ) -> None:
        """Run sequential auto-turn rounds through eligible members.

        After each response, parses @mentions and bumps mentioned members
        to the front of the remaining queue for the current round.
        """
        if self.auto_rounds <= 0:
            return
        for _round in range(self.auto_rounds):
            active = targets.copy()
            if shuffle:
                import random

                random.shuffle(active)
            queue = list(active)
            while queue:
                if self.interrupted or self.generation != generation:
                    return
                name = queue.pop(0)
                if not self.claim_delivery_target(name):
                    continue
                member = self.council.get_member(name)
                if not member:
                    continue
                log = self.query_one("#message-log", MessageLog)
                log.scroll_if_following()
                await self.await_remove_member_panels(log, name)
                if not log.query(f"#wait-{name}"):
                    log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
                stream_path = tdir / f".stream-{name}.jsonl"
                body = await self.run_query(member, stream_path, generation=generation)
                if body and queue:
                    queue = mention_bump(body, queue, self.member_names)

    def remove_member_panels(self, log: MessageLog, name: str) -> None:
        """Remove any existing wait/stream/thinking/interrupted panels for a member."""
        for prefix in ("wait", "stream", "thinking", "interrupted"):
            for panel in list(log.query(f"#{prefix}-{name}")):
                panel.remove()

    async def await_remove_member_panels(self, log: MessageLog, name: str) -> None:
        """Remove member panels and wait for DOM to update (for async callers)."""
        removals = []
        for prefix in ("wait", "stream", "thinking", "interrupted"):
            for panel in list(log.query(f"#{prefix}-{name}")):
                removals.append(panel.remove())
        for awaitable in removals:
            await awaitable

    def parse_targets(self, text: str) -> list[str]:
        """Parse @mentions from text to determine query targets.

        Muted members are excluded from broadcast but can be explicitly @mentioned.
        Returns list of member names to query.
        """
        mentions = re.findall(r"(?<!\w)@(\w+)", text)

        if not mentions:
            # Broadcast: exclude muted members
            return [m for m in self.member_names if m not in self.muted]

        if "all" in mentions:
            return [m for m in self.member_names if m not in self.muted]

        # Explicit @mention overrides mute
        valid = [m for m in mentions if m in self.member_names]
        return valid if valid else [m for m in self.member_names if m not in self.muted]

    # -- Slash commands ---------------------------------------------------

    def handle_slash_command(self, text: str) -> None:
        """Dispatch slash commands."""
        from .widgets import suggest_command

        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/mute":
            self.cmd_mute(arg)
        elif cmd == "/unmute":
            self.cmd_unmute(arg)
        elif cmd == "/copy":
            self.cmd_copy(arg)
        elif cmd in ("/writable", "/writeable"):
            self.cmd_writable()
        elif cmd == "/status":
            self.cmd_status()
        elif cmd in ("/help", "/h"):
            self.cmd_help()
        elif cmd in ("/quit", "/exit"):
            self.exit()
        else:
            suggestion = suggest_command(cmd)
            if suggestion:
                self.show_system_message(
                    f"Unknown command: {cmd}. Did you mean {suggestion}? Type /help for available commands."
                )
            else:
                self.show_system_message(f"Unknown command: {cmd}. Type /help for available commands.")

    def cmd_mute(self, arg: str) -> None:
        """Mute a member — exclude from broadcast queries."""
        if not arg:
            if self.muted:
                self.show_system_message(f"Muted: {', '.join(sorted(self.muted))}")
            else:
                self.show_system_message("No members muted. Usage: /mute <member>")
            return
        name = arg.lower()
        if name not in self.member_names:
            self.show_system_message(f"Unknown member: {name}. Members: {', '.join(self.member_names)}")
            return
        if name in self.muted:
            self.show_system_message(f"{name} is already muted.")
            return
        self.muted.add(name)
        self.show_system_message(f"Muted {name} — excluded from broadcast queries.")

    def cmd_unmute(self, arg: str) -> None:
        """Unmute a member — re-include in broadcast queries."""
        if not arg:
            self.show_system_message("Usage: /unmute <member>")
            return
        name = arg.lower()
        if name not in self.muted:
            self.show_system_message(f"{name} is not muted.")
            return
        self.muted.discard(name)
        self.show_system_message(f"Unmuted {name} — included in broadcast queries.")

    def cmd_copy(self, arg: str) -> None:
        """Copy the last agent response to the system clipboard."""
        from .clipboard import ClipboardUnavailableError, copy_to_clipboard

        messages = list_messages(self.base, self.branch, self.thread_id)
        # Filter to non-king messages
        member_filter = arg.lower() if arg else None
        candidates = [m for m in messages if m.from_ != "king"]
        if member_filter:
            candidates = [m for m in candidates if m.from_ == member_filter]
            if not candidates:
                self.show_system_message(f"No messages from {member_filter}.")
                return

        if not candidates:
            self.show_system_message("No messages to copy.")
            return

        last = candidates[-1]
        try:
            copy_to_clipboard(last.body)
            label = f" from {last.from_}" if member_filter else " last response"
            self.show_system_message(f"Copied{label} to clipboard.")
        except ClipboardUnavailableError:
            self.show_system_message("Clipboard unavailable. Install xclip or xsel.")
        except Exception as exc:
            self.show_system_message(f"Copy failed: {exc}")

    def cmd_writable(self) -> None:
        """Toggle writable mode for all council members."""
        self.writable = not self.writable
        if self.council:
            branch_context = build_branch_context(self.base, self.branch)
            preamble_template = WRITABLE_CHAT_PREAMBLE if self.writable else CHAT_PREAMBLE
            for member in self.council.members:
                member.writable = self.writable
                member.preamble = preamble_template.format(name=member.name) + branch_context
        label = "ON — members can edit files and run commands" if self.writable else "OFF — advisory only"
        self.show_system_message(f"Writable mode: {label}")

    def cmd_status(self) -> None:
        """Show the branch's tickets and execution-context assignments."""
        self.show_system_message(build_branch_context(self.base, self.branch).rstrip())

    def cmd_help(self) -> None:
        """Show available commands."""
        help_text = (
            "/mute <member>  — exclude member from broadcast queries\n"
            "/unmute <member> — re-include member in queries\n"
            "/copy [member]   — copy last agent response to clipboard\n"
            "/writable        — toggle writable mode (file edits, commands)\n"
            "/status          — show branch tickets and concurrent agent contexts\n"
            "/mute            — show currently muted members\n"
            "/help            — show this help\n"
            "/quit or /exit   — quit kd council chat\n"
            "\n"
            "Esc: interrupt running queries / quit\n"
            "Enter: send message\n"
            "Shift+Enter: newline\n"
            "Tab: autocomplete @mention or /command (cycle with repeated Tab)\n"
            "End: jump to bottom (re-engage auto-follow)\n"
            "Ctrl+T: toggle thinking visibility (auto/show/hide)\n"
            "@member: direct message\n"
            "@all: explicit broadcast\n"
            "Click message: reply (@mention)\n"
            "Shift+click message: copy to clipboard"
        )
        self.show_system_message(help_text)

    def show_system_message(self, text: str) -> None:
        """Show a system message in the message log."""
        log = self.query_one("#message-log", MessageLog)
        log.scroll_if_following()  # capture intent BEFORE mount
        panel = Static(text, classes="system-message")
        log.mount(panel)

    # -- Polling ----------------------------------------------------------

    def poll_updates(self) -> None:
        """Called every 100ms to check for new data."""
        if self.poller is None:
            return

        events = self.poller.poll()
        if not events:
            return

        log = self.query_one("#message-log", MessageLog)
        log.scroll_if_following()  # capture intent BEFORE processing events

        for event in events:
            if isinstance(event, NewMessage):
                self.handle_new_message(log, event)
            elif isinstance(event, StreamStarted):
                self.handle_stream_started(log, event)
            elif isinstance(event, ThinkingDelta):
                self.handle_thinking_delta(log, event)
            elif isinstance(event, StreamDelta):
                self.handle_stream_delta(log, event)
            elif isinstance(event, ToolUseEvent):
                self.handle_tool_use(log, event)
            elif isinstance(event, StreamFinished):
                self.handle_stream_finished(event)

        # Update status bar to reflect scroll state
        self.update_status_bar(log)

    def handle_new_message(self, log: MessageLog, event: NewMessage) -> None:
        """Replace waiting/streaming/thinking/interrupted panel in-place with a finalized message."""
        if event.sequence in self.rendered_message_sequences:
            self.rendered_message_sequences.discard(event.sequence)
            return

        waiting_id = f"wait-{event.sender}"
        streaming_id = f"stream-{event.sender}"
        thinking_id = f"thinking-{event.sender}"
        interrupted_id = f"interrupted-{event.sender}"
        existing = (
            list(log.query(f"#{waiting_id}"))
            + list(log.query(f"#{streaming_id}"))
            + list(log.query(f"#{interrupted_id}"))
        )

        # Handle thinking panel persistence — replace with sequence-specific id
        # (Textual forbids reassigning .id after mount, so we remove + remount)
        thinking_panels = list(log.query(f"#{thinking_id}"))
        if thinking_panels:
            old_panel = thinking_panels[0]
            new_panel = ThinkingPanel(sender=event.sender, id=f"thinking-{event.sender}-{event.sequence}")
            new_panel.thinking_text = old_panel.thinking_text
            new_panel.start_time = old_panel.start_time
            new_panel.user_pinned = old_panel.user_pinned
            new_panel.expanded = old_panel.expanded
            log.mount(new_panel, before=old_panel)
            old_panel.remove()
            if self.thinking_visibility == "auto":
                new_panel.collapse()

        # Detect error/interrupted responses from thread message body
        if event.sender != "king" and is_error_response(event.body):
            timed_out = is_timeout_response(event.body)
            panel = ErrorPanel(
                sender=event.sender,
                error=event.body,
                timed_out=timed_out,
                id=f"msg-{event.sequence}",
            )
        elif event.sender != "king" and is_interrupted_response(event.body):
            panel = ErrorPanel(
                sender=event.sender,
                error=event.body,
                timed_out=False,
                id=f"msg-{event.sequence}",
            )
        else:
            panel = MessagePanel(
                sender=event.sender,
                body=event.body,
                member_names=self.member_names,
                timestamp=format_timestamp(datetime.now(UTC)),
                id=f"msg-{event.sequence}",
            )

        if existing:
            log.mount(panel, before=existing[0])
            for w in existing:
                w.remove()
        else:
            log.mount(panel)

    def handle_stream_started(self, log: MessageLog, event: StreamStarted) -> None:
        """Replace waiting panel in-place with streaming panel."""
        waiting_id = f"wait-{event.member}"
        streaming_id = f"stream-{event.member}"

        existing = list(log.query(f"#{waiting_id}")) + list(log.query(f"#{streaming_id}"))

        panel = StreamingPanel(sender=event.member, id=streaming_id)
        if existing:
            log.mount(panel, before=existing[0])
            for w in existing:
                w.remove()
        else:
            log.mount(panel)

    def handle_thinking_delta(self, log: MessageLog, event: ThinkingDelta) -> None:
        """Show or update a ThinkingPanel for this member."""
        if self.thinking_visibility == "hide":
            return

        panel_id = f"thinking-{event.member}"
        existing = list(log.query(f"#{panel_id}"))
        if existing:
            panel = existing[0]
            panel.update_thinking(event.full_text)
            return

        panel = ThinkingPanel(sender=event.member, id=panel_id)
        stream_id = f"stream-{event.member}"
        wait_id = f"wait-{event.member}"
        anchor = list(log.query(f"#{stream_id}")) + list(log.query(f"#{wait_id}"))
        if anchor:
            log.mount(panel, before=anchor[0])
        else:
            log.mount(panel)
        panel.update_thinking(event.full_text)

    def handle_stream_delta(self, log: MessageLog, event: StreamDelta) -> None:
        """Update the streaming panel with new text. Auto-collapse thinking."""
        # Auto-collapse thinking panel on first answer token
        if self.thinking_visibility == "auto":
            thinking_id = f"thinking-{event.member}"
            panels = list(log.query(f"#{thinking_id}"))
            if panels:
                thinking_panel = panels[0]
                thinking_panel.collapse()

        panel_id = f"stream-{event.member}"
        panels = list(log.query(f"#{panel_id}"))
        if panels:
            panel = panels[0]
            panel.update_content(event.full_text)

    def handle_tool_use(self, log: MessageLog, event: ToolUseEvent) -> None:
        """Show tool-use activity on the streaming panel's border subtitle."""
        panel_id = f"stream-{event.member}"
        panels = list(log.query(f"#{panel_id}"))
        if panels:
            panels[0].border_subtitle = f"using {event.tool_name}"

    def handle_stream_finished(self, event: StreamFinished) -> None:
        """Remove the streaming panel (finalized message replaces it)."""
        panel_id = f"stream-{event.member}"
        panels = list(self.query(f"#{panel_id}"))
        if panels:
            panels[0].remove()
