"""ChatApp — main Textual application for kd chat."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import VerticalScroll
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
    is_timeout_response,
    list_messages,
    thread_dir,
)

from .poll import NewMessage, StreamDelta, StreamFinished, StreamStarted, ThreadPoller
from .widgets import ErrorPanel, MessagePanel, StreamingPanel, WaitingPanel

CHAT_PREAMBLE = (
    "You are {name}, participating in a group discussion with other AI agents and the King (human). "
    "Engage directly with the conversation — respond to questions, share your perspective, "
    "and build on or challenge points raised by others. "
    "Do NOT create, edit, or write files. Do NOT run git commands that modify state.\n\n"
)


class MessageLog(VerticalScroll):
    """Scrollable container for chat messages."""

    DEFAULT_CSS = """
    MessageLog {
        height: 1fr;
    }
    """


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
    """

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: auto;
        min-height: 3;
        max-height: 10;
    }
    """

    class Submit(Message):
        """Posted when the user presses Enter to send."""

    async def _on_key(self, event) -> None:
        if event.key == "enter" and "shift" not in event.key:
            event.stop()
            event.prevent_default()
            self.post_message(self.Submit())
            return
        await super()._on_key(event)


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
    ]

    def __init__(self, base: Path, branch: str, thread_id: str) -> None:
        super().__init__()
        self.base = base
        self.branch = branch
        self.thread_id = thread_id
        self.poller: ThreadPoller | None = None
        self.member_names: list[str] = []
        self.auto_scroll = True
        self.council: Council | None = None
        self.interrupted = False
        self.muted: set[str] = set()

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
        yield StatusBar("Esc: interrupt/quit · Enter: send · Shift+Enter: newline")
        yield InputArea(id="input-area")

    def on_mount(self) -> None:
        """Initialize poller, council, and start polling."""
        tdir = thread_dir(self.base, self.branch, self.thread_id)

        # Resolve member backends for stream text extraction
        cfg = load_config(self.base)
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

        # Create Council for direct query dispatch (no load_sessions — chat threads
        # use format_thread_history() for context, not session resume IDs)
        self.council = Council.create(base=self.base)
        # Set base/branch and chat-specific preamble on members
        for member in self.council.members:
            member.base = self.base
            member.branch = self.branch
            member.preamble = CHAT_PREAMBLE.format(name=member.name)

        # Load existing messages from thread history
        self.load_history()

        self.set_interval(0.1, self.poll_updates)

        # Focus the input area
        input_area = self.query_one("#input-area", TextArea)
        input_area.focus()

    def action_interrupt(self) -> None:
        """Handle Escape: interrupt running queries or quit.

        First Escape kills active queries and shows interrupted panels.
        Second Escape (or Escape with nothing running) quits the app.
        """
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
            for prefix in ("wait", "stream"):
                panel_id = f"{prefix}-{member.name}"
                try:
                    panel = log.query_one(f"#{panel_id}")
                    error_panel = ErrorPanel(
                        sender=member.name,
                        error="*Interrupted*",
                        id=f"interrupted-{member.name}",
                    )
                    log.mount(error_panel, before=panel)
                    panel.remove()
                except Exception:
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
            else:
                panel = MessagePanel(
                    sender=msg.from_,
                    body=msg.body,
                    id=f"msg-{msg.sequence}",
                )
            log.mount(panel)

        # Update poller so it doesn't re-report these messages
        if self.poller and messages:
            self.poller.last_sequence = messages[-1].sequence

        # Scroll to bottom after loading history
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

        # Parse @mentions
        targets = self.parse_targets(text)

        # Write king message to thread files
        to = targets[0] if len(targets) == 1 else "all"
        add_message(self.base, self.branch, self.thread_id, from_="king", to=to, body=text)

        # Render king message immediately (don't wait for poll cycle)
        log = self.query_one("#message-log", MessageLog)
        king_panel = MessagePanel(sender="king", body=text, id=f"king-{id(text)}")
        log.mount(king_panel)

        # Update poller so it doesn't re-report this king message
        if self.poller:
            self.poller.last_sequence += 1

        # Create waiting panels and dispatch queries
        tdir = thread_dir(self.base, self.branch, self.thread_id)

        for name in targets:
            panel = WaitingPanel(sender=name, id=f"wait-{name}")
            log.mount(panel)

            # Launch query in background
            member = self.council.get_member(name) if self.council else None
            if member:
                stream_path = tdir / f".stream-{name}.jsonl"
                self.run_worker(self.run_query(member, text, stream_path), exclusive=False)

        if self.auto_scroll:
            log.scroll_end(animate=False)

    async def run_query(self, member, prompt: str, stream_path: Path) -> None:
        """Run a member query with full thread context, then persist and clean up."""
        try:
            timeout = self.council.timeout if self.council else 600
            tdir = thread_dir(self.base, self.branch, self.thread_id)
            prompt_with_history = format_thread_history(tdir, member.name)
            response = await asyncio.to_thread(member.query, prompt_with_history, timeout, stream_path, max_retries=0)

            # Use cleaner message for interrupted queries with no useful text
            if self.interrupted and not response.text:
                body = "*Interrupted*"
            else:
                body = response.thread_body()

            # Always persist response to thread files (source of truth)
            add_message(self.base, self.branch, self.thread_id, from_=member.name, to="king", body=body)

        except Exception as exc:
            # Persist the exception as an error message
            error_body = f"*Error: {exc}*"
            add_message(self.base, self.branch, self.thread_id, from_=member.name, to="king", body=error_body)
        finally:
            # Clean up stream file — the finalized message file is now the source of truth
            if stream_path.exists():
                stream_path.unlink()

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
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/mute":
            self.cmd_mute(arg)
        elif cmd == "/unmute":
            self.cmd_unmute(arg)
        elif cmd in ("/help", "/h"):
            self.cmd_help()
        elif cmd in ("/quit", "/exit"):
            self.exit()
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

    def cmd_help(self) -> None:
        """Show available commands."""
        help_text = (
            "/mute <member>  — exclude member from broadcast queries\n"
            "/unmute <member> — re-include member in queries\n"
            "/mute            — show currently muted members\n"
            "/help            — show this help\n"
            "/quit or /exit   — quit kd chat\n"
            "\n"
            "Esc: interrupt running queries / quit\n"
            "Enter: send message\n"
            "Shift+Enter: newline\n"
            "@member: direct message\n"
            "@all: explicit broadcast"
        )
        self.show_system_message(help_text)

    def show_system_message(self, text: str) -> None:
        """Show a system message in the message log."""
        log = self.query_one("#message-log", MessageLog)
        panel = Static(text, classes="system-message")
        log.mount(panel)
        if self.auto_scroll:
            log.scroll_end(animate=False)

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
            elif isinstance(event, StreamDelta):
                self.handle_stream_delta(event)
            elif isinstance(event, StreamFinished):
                self.handle_stream_finished(event)

        if self.auto_scroll:
            log.scroll_end(animate=False)

    def handle_new_message(self, log: MessageLog, event: NewMessage) -> None:
        """Replace waiting/streaming/interrupted panel in-place with a finalized message."""
        waiting_id = f"wait-{event.sender}"
        streaming_id = f"stream-{event.sender}"
        interrupted_id = f"interrupted-{event.sender}"
        existing = (
            list(log.query(f"#{waiting_id}"))
            + list(log.query(f"#{streaming_id}"))
            + list(log.query(f"#{interrupted_id}"))
        )

        # Detect error responses from thread message body
        if event.sender != "king" and is_error_response(event.body):
            timed_out = is_timeout_response(event.body)
            panel = ErrorPanel(
                sender=event.sender,
                error=event.body,
                timed_out=timed_out,
                id=f"msg-{event.sequence}",
            )
        else:
            panel = MessagePanel(
                sender=event.sender,
                body=event.body,
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

    def handle_stream_delta(self, event: StreamDelta) -> None:
        """Update the streaming panel with new text."""
        panel_id = f"stream-{event.member}"
        try:
            panel = self.query_one(f"#{panel_id}", StreamingPanel)
            panel.update_content(event.full_text)
        except Exception:
            pass  # Panel may have been replaced by finalized message

    def handle_stream_finished(self, event: StreamFinished) -> None:
        """Remove the streaming panel (finalized message replaces it)."""
        panel_id = f"stream-{event.member}"
        try:
            panel = self.query_one(f"#{panel_id}")
            panel.remove()
        except Exception:
            pass
