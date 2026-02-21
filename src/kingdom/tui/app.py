"""ChatApp — main Textual application for kd chat."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult, ScreenStackError
from textual.binding import BindingType
from textual.containers import VerticalScroll
from textual.css.query import QueryError
from textual.message import Message
from textual.widgets import Static, TextArea

from kingdom.agent import resolve_all_agents
from kingdom.config import load_config
from kingdom.council import Council
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

from .poll import NewMessage, StreamDelta, StreamFinished, StreamStarted, ThinkingDelta, ThreadPoller
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

CHAT_PREAMBLE = (
    "You are {name}, participating in a group discussion with other AI agents and the King (human). "
    "Engage directly with the conversation — respond to questions, share your perspective, "
    "and build on or challenge points raised by others. "
    "Do NOT create, edit, or write files. Do NOT run git commands that modify state.\n\n"
)

WRITABLE_CHAT_PREAMBLE = (
    "You are {name}, participating in a group discussion with other AI agents and the King (human). "
    "You have full permissions — you may edit files, create tickets, run git commands, "
    "and execute any action the King requests. Act on instructions directly.\n\n"
)


def build_branch_context(base: Path, branch: str) -> str:
    """Build a context block with the current branch name and ticket summary.

    Returns a string like::

        [Branch context]
        Branch: feature/my-feature
        Tickets:
          e0eb  in_progress  P2  kd chat: inject branch context
          a1b2  open         P1  Fix parsing bug

    Returns an empty string if no branch info is available.
    """
    from kingdom.state import branch_root
    from kingdom.ticket import list_tickets

    lines = ["[Branch context]", f"Branch: {branch}"]

    tickets_dir = branch_root(base, branch) / "tickets"
    tickets = [t for t in list_tickets(tickets_dir) if t.status != "closed"]
    if tickets:
        lines.append("Tickets:")
        for t in tickets:
            status = t.status.replace("_", " ")
            lines.append(f"  {t.id}  {status:12s}  P{t.priority}  {t.title}")

    return "\n".join(lines) + "\n\n"


class MessageLog(VerticalScroll):
    """Scrollable container for chat messages.

    Wraps Textual's VerticalScroll with smart auto-scroll: new content only
    scrolls to bottom when the user is already near the bottom.  If the user
    has scrolled up to read history, the view stays put.

    ``is_following`` — True when auto-scroll is active (user is near bottom).
    ``SCROLL_THRESHOLD`` — pixel distance from bottom that counts as "near".
    """

    SCROLL_THRESHOLD: int = 5

    DEFAULT_CSS = """
    MessageLog {
        height: 1fr;
    }
    """

    @property
    def is_following(self) -> bool:
        """True when the viewport is at or near the bottom.

        Uses the internal ``_anchor_released`` flag from Textual's anchor
        mechanism.  When the user scrolls up, Textual releases the anchor;
        when they scroll back to the bottom, it re-engages.
        """
        return not self._anchor_released

    def scroll_if_following(self) -> None:
        """Scroll to bottom if the user hasn't scrolled up.

        Textual's anchor() alone doesn't reliably scroll when new widgets
        are mounted.  Call this after mounting content to keep the view
        pinned to the bottom while respecting manual scroll-up.
        """
        if self.is_following:
            self.scroll_end(animate=False)


class StatusBar(Static):
    """Keybinding hints at the bottom."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """


class InputArea(TextArea):
    """User input area at the bottom of the screen.

    Enter sends the message (posts Submit to the app).
    Shift+Enter inserts a newline.
    Tab after @partial completes member names.
    """

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: auto;
        min-height: 3;
        max-height: 10;
        scrollbar-size-vertical: 0;
    }
    """

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
        if event.key == "enter" and "shift" not in event.key:
            event.stop()
            event.prevent_default()
            self.post_message(self.Submit())
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


class ChatApp(App):
    """Council chat TUI."""

    TITLE = "kd chat"

    CSS = """
    Screen {
        layout: vertical;
    }
    .system-message {
        margin: 0 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "interrupt", "Interrupt/Quit"),
        ("end", "scroll_bottom", "Jump to bottom"),
        ("ctrl+t", "toggle_thinking", "Toggle thinking"),
    ]

    THINKING_CYCLE: ClassVar[list[str]] = ["auto", "show", "hide"]

    def __init__(
        self, base: Path, branch: str, thread_id: str, debug_streams: bool = False, writable: bool = False
    ) -> None:
        super().__init__()
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

    def compose(self) -> ComposeResult:
        # Load thread metadata for header
        try:
            meta = get_thread(self.base, self.branch, self.thread_id)
            self.member_names = [m for m in meta.members if m != "king"]
        except FileNotFoundError:
            self.member_names = []

        members_str = " ".join(self.member_names) if self.member_names else "no members"
        yield Static(
            f"kd chat · {self.thread_id} · {members_str}",
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

        # Load config for backends and thinking visibility
        cfg = load_config(self.base)
        self.thinking_visibility = cfg.council.thinking_visibility
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

        # Enable smart auto-scroll: follows new content when at/near the
        # bottom, pauses when user scrolls up, re-engages when they return.
        log = self.query_one("#message-log", MessageLog)
        log.anchor()

        self.set_interval(0.1, self.poll_updates)

        # Focus the input area
        input_area = self.query_one("#input-area", TextArea)
        input_area.focus()

    def action_scroll_bottom(self) -> None:
        """Jump to bottom and re-engage auto-follow."""
        log = self.query_one("#message-log", MessageLog)
        log.scroll_end(animate=False)
        log.anchor()
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
            if msg.from_ != "king" and is_error_response(msg.body):
                timed_out = is_timeout_response(msg.body)
                panel = ErrorPanel(
                    sender=msg.from_,
                    error=msg.body,
                    timed_out=timed_out,
                    id=f"msg-{msg.sequence}",
                )
            elif msg.from_ != "king" and is_interrupted_response(msg.body):
                panel = ErrorPanel(
                    sender=msg.from_,
                    error=msg.body,
                    timed_out=False,
                    id=f"msg-{msg.sequence}",
                )
            else:
                panel = MessagePanel(
                    sender=msg.from_,
                    body=msg.body,
                    member_names=self.member_names,
                    id=f"msg-{msg.sequence}",
                )
            log.mount(panel)

        # Update poller so it doesn't re-report these messages
        if self.poller and messages:
            self.poller.last_sequence = messages[-1].sequence

        log.scroll_end(animate=False)

    def on_key(self, event) -> None:
        """Handle Enter to send, let Shift+Enter pass through for newline."""
        if event.key == "enter":
            input_area = self.query_one("#input-area", TextArea)
            if input_area.has_focus:
                event.prevent_default()
                self.send_message()

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
        """Handle reply: prefill input with @sender mention."""
        reply_text = format_reply_text(event.sender)
        input_area = self.query_one("#input-area", InputArea)
        existing = input_area.text
        if existing.strip():
            input_area.load_text(reply_text + existing)
        else:
            input_area.load_text(reply_text)
        input_area.focus()
        # Cursor ends up at (0,0) after load_text — move to end of the @mention prefix
        input_area.move_cursor_relative(columns=len(reply_text))

    def send_message(self) -> None:
        """Send the current input as a king message or handle slash command."""
        input_area = self.query_one("#input-area", TextArea)
        text = input_area.text.strip()
        if not text:
            return

        input_area.clear()

        # Handle slash commands
        if text.startswith("/"):
            self.handle_slash_command(text)
            return

        self.interrupted = False
        self.generation += 1
        gen = self.generation

        # Parse @mentions
        targets = self.parse_targets(text)

        # Write king message to thread files
        to = targets[0] if len(targets) == 1 else "all"
        add_message(self.base, self.branch, self.thread_id, from_="king", to=to, body=text)

        # Render king message immediately (don't wait for poll cycle)
        log = self.query_one("#message-log", MessageLog)
        king_panel = MessagePanel(sender="king", body=text, member_names=self.member_names, id=f"king-{id(text)}")
        log.mount(king_panel)

        # Update poller so it doesn't re-report this king message
        if self.poller:
            self.poller.last_sequence += 1

        tdir = thread_dir(self.base, self.branch, self.thread_id)

        # Clean up any in-flight panels from previous exchange to avoid
        # duplicate widget IDs when mounting new WaitingPanels.
        for name in targets:
            self.remove_member_panels(log, name)

        if to == "all":
            # Broadcast: always query all targets in parallel, then optionally
            # run auto-turn follow-ups (sequential round-robin).
            for name in targets:
                log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
            prior_messages = list_messages(self.base, self.branch, self.thread_id)
            is_first_exchange = not any(m.from_ != "king" for m in prior_messages)
            self.run_worker(self.run_chat_round(targets, gen, tdir, is_first_exchange), exclusive=False)
        else:
            # Directed: single query, no auto-turns
            log.mount(WaitingPanel(sender=targets[0], id=f"wait-{targets[0]}"))
            member = self.council.get_member(targets[0]) if self.council else None
            if member:
                stream_path = tdir / f".stream-{targets[0]}.jsonl"
                self.run_worker(self.run_query(member, stream_path, generation=gen), exclusive=False)

        log.scroll_if_following()

    async def run_query(self, member, stream_path: Path, generation: int | None = None) -> None:
        """Run a member query with full thread context, then persist and clean up.

        When *generation* is passed, the response is discarded if ``self.generation``
        has moved on (meaning the user sent a new message while this query was in flight).
        """
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
                return

            # Use cleaner message for interrupted queries with no useful text
            if self.interrupted and not response.text:
                body = "*Interrupted*"
            elif self.interrupted and response.text:
                body = response.thread_body() + "\n\n*[Interrupted — response may be incomplete]*"
            else:
                body = response.thread_body()

            # Always persist response to thread files (source of truth)
            add_message(self.base, self.branch, self.thread_id, from_=member.name, to="king", body=body)

        except (OSError, RuntimeError, ValueError) as exc:
            # Persist the exception as an error message
            logger.exception("Member query failed for %s", member.name)
            error_body = f"*Error: {exc}*"
            add_message(self.base, self.branch, self.thread_id, from_=member.name, to="king", body=error_body)
        finally:
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

    def build_debug_stream_path(self, stream_path: Path, member_name: str) -> Path:
        """Build a unique path for preserved stream debug artifacts."""
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return stream_path.parent / f".debug-stream-{member_name}-{timestamp}.jsonl"

    async def run_chat_round(self, targets: list[str], generation: int, tdir: Path, is_first_exchange: bool) -> None:
        """Coordinate a chat round after the king sends a message.

        Always starts with a parallel broadcast for the initial response to the
        king's message.  On follow-up exchanges (not the first), continues with
        sequential round-robin auto-turns after the broadcast.
        """
        if not self.council:
            return

        # Parallel broadcast (or sequential if configured).  WaitingPanels
        # are already mounted by send_message().
        mode = self.council.mode
        if mode == "broadcast" and len(targets) > 1:
            coros = []
            for name in targets:
                member = self.council.get_member(name)
                if member:
                    stream_path = tdir / f".stream-{name}.jsonl"
                    coros.append(self.run_query(member, stream_path, generation=generation))
            await asyncio.gather(*coros)
            if self.generation != generation:
                return
        else:
            for name in targets:
                if self.interrupted or self.generation != generation:
                    return
                member = self.council.get_member(name)
                if not member:
                    continue
                stream_path = tdir / f".stream-{name}.jsonl"
                await self.run_query(member, stream_path, generation=generation)

        # First exchange: broadcast only, no auto-turns.
        if is_first_exchange:
            return

        # Follow-up: sequential round-robin auto-turns after the broadcast.
        active = [n for n in self.member_names if n not in self.muted]
        budget = self.council.auto_messages
        if budget == 0:
            return
        if budget < 0:
            # -1 = auto: one message per active member
            budget = len(active)
        if budget <= 0:
            return
        messages_sent = 0

        while messages_sent < budget:
            for name in active:
                if messages_sent >= budget:
                    break
                if self.interrupted or self.generation != generation:
                    return
                if name in self.muted:
                    continue
                member = self.council.get_member(name)
                if not member:
                    continue
                # Mount WaitingPanel for this member's turn
                log = self.query_one("#message-log", MessageLog)
                self.remove_member_panels(log, name)
                log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
                log.scroll_if_following()
                stream_path = tdir / f".stream-{name}.jsonl"
                await self.run_query(member, stream_path, generation=generation)
                messages_sent += 1

    def remove_member_panels(self, log: MessageLog, name: str) -> None:
        """Remove any existing wait/stream/thinking/interrupted panels for a member."""
        for prefix in ("wait", "stream", "thinking", "interrupted"):
            for panel in list(log.query(f"#{prefix}-{name}")):
                panel.remove()

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
        elif cmd in ("/writable", "/writeable"):
            self.cmd_writable()
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

    def cmd_help(self) -> None:
        """Show available commands."""
        help_text = (
            "/mute <member>  — exclude member from broadcast queries\n"
            "/unmute <member> — re-include member in queries\n"
            "/writable        — toggle writable mode (file edits, commands)\n"
            "/mute            — show currently muted members\n"
            "/help            — show this help\n"
            "/quit or /exit   — quit kd chat\n"
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
        panel = Static(text, classes="system-message")
        log.mount(panel)
        log.scroll_if_following()

    # -- Polling ----------------------------------------------------------

    def poll_updates(self) -> None:
        """Called every 100ms to check for new data."""
        if self.poller is None:
            return

        events = self.poller.poll()
        if not events:
            return

        log = self.query_one("#message-log", MessageLog)

        for event in events:
            if isinstance(event, NewMessage):
                self.handle_new_message(log, event)
            elif isinstance(event, StreamStarted):
                self.handle_stream_started(log, event)
            elif isinstance(event, ThinkingDelta):
                self.handle_thinking_delta(log, event)
            elif isinstance(event, StreamDelta):
                self.handle_stream_delta(log, event)
            elif isinstance(event, StreamFinished):
                self.handle_stream_finished(event)

        log.scroll_if_following()

        # Update status bar to reflect scroll state
        self.update_status_bar(log)

    def handle_new_message(self, log: MessageLog, event: NewMessage) -> None:
        """Replace waiting/streaming/thinking/interrupted panel in-place with a finalized message."""
        waiting_id = f"wait-{event.sender}"
        streaming_id = f"stream-{event.sender}"
        thinking_id = f"thinking-{event.sender}"
        interrupted_id = f"interrupted-{event.sender}"
        existing = (
            list(log.query(f"#{waiting_id}"))
            + list(log.query(f"#{streaming_id}"))
            + list(log.query(f"#{interrupted_id}"))
        )

        # Handle thinking panel persistence
        thinking_panels = list(log.query(f"#{thinking_id}"))
        if thinking_panels:
            thinking_panel = thinking_panels[0]
            if self.thinking_visibility == "auto":
                thinking_panel.collapse()
            thinking_panel.id = f"thinking-{event.sender}-{event.sequence}"

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

    def handle_stream_finished(self, event: StreamFinished) -> None:
        """Remove the streaming panel (finalized message replaces it)."""
        panel_id = f"stream-{event.member}"
        panels = list(self.query(f"#{panel_id}"))
        if panels:
            panels[0].remove()
