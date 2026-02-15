"""ChatApp — main Textual application for kd chat."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import VerticalScroll
from textual.widgets import Static, TextArea

from kingdom.agent import resolve_all_agents
from kingdom.config import load_config
from kingdom.council import Council
from kingdom.thread import add_message, get_thread, is_error_response, is_timeout_response, list_messages, thread_dir

from .poll import NewMessage, StreamDelta, StreamFinished, StreamStarted, ThreadPoller
from .widgets import ErrorPanel, MessagePanel, StreamingPanel, WaitingPanel


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
    """User input area at the bottom of the screen."""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: auto;
        min-height: 3;
        max-height: 10;
    }
    """


class ChatApp(App):
    """Council chat TUI."""

    TITLE = "kd chat"

    CSS = """
    Screen {
        layout: vertical;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "quit", "Quit"),
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
        yield StatusBar("Esc: quit · Enter: send · Shift+Enter: newline")
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

        # Create Council for direct query dispatch
        self.council = Council.create(base=self.base)
        self.council.load_sessions(self.base, self.branch)
        # Set base/branch on members for PID tracking
        for member in self.council.members:
            member.base = self.base
            member.branch = self.branch

        # Load existing messages from thread history
        self.load_history()

        self.set_interval(0.1, self.poll_updates)

        # Focus the input area
        input_area = self.query_one("#input-area", TextArea)
        input_area.focus()

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

    def send_message(self) -> None:
        """Send the current input as a king message."""
        input_area = self.query_one("#input-area", TextArea)
        text = input_area.text.strip()
        if not text:
            return

        input_area.clear()

        # Parse @mentions
        targets = self.parse_targets(text)

        # Write king message to thread files
        to = targets[0] if len(targets) == 1 else "all"
        add_message(self.base, self.branch, self.thread_id, from_="king", to=to, body=text)

        # Create waiting panels and dispatch queries
        log = self.query_one("#message-log", MessageLog)
        tdir = thread_dir(self.base, self.branch, self.thread_id)

        for name in targets:
            panel = WaitingPanel(sender=name, id=f"panel-{name}")
            log.mount(panel)

            # Launch query in background
            member = self.council.get_member(name) if self.council else None
            if member:
                stream_path = tdir / f".stream-{name}.jsonl"
                asyncio.get_event_loop().create_task(self.run_query(member, text, stream_path))

        if self.auto_scroll:
            log.scroll_end(animate=False)

    async def run_query(self, member, prompt: str, stream_path: Path) -> None:
        """Run a member query in a thread and handle errors."""
        try:
            timeout = self.council.timeout if self.council else 600
            response = await asyncio.to_thread(member.query, prompt, timeout, stream_path)
            if response.error and not response.text:
                timed_out = "Timeout" in response.error
                log = self.query_one("#message-log", MessageLog)
                panel = ErrorPanel(
                    sender=member.name,
                    error=response.error,
                    timed_out=timed_out,
                    id=f"error-{member.name}",
                )
                # Remove waiting/streaming panel
                panel_id = f"panel-{member.name}"
                for existing in log.query(f"#{panel_id}"):
                    existing.remove()
                log.mount(panel)
        except Exception as exc:
            log = self.query_one("#message-log", MessageLog)
            panel = ErrorPanel(
                sender=member.name,
                error=str(exc),
                id=f"error-{member.name}",
            )
            log.mount(panel)

    def parse_targets(self, text: str) -> list[str]:
        """Parse @mentions from text to determine query targets.

        Returns list of member names to query.
        """
        mentions = re.findall(r"(?<!\w)@(\w+)", text)

        if not mentions:
            return list(self.member_names)

        if "all" in mentions:
            return list(self.member_names)

        # Filter to valid member names
        valid = [m for m in mentions if m in self.member_names]
        return valid if valid else list(self.member_names)

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
        """Add a finalized message panel (or error panel) to the log."""
        # Remove any existing streaming/waiting panel for this sender
        panel_id = f"panel-{event.sender}"
        for widget in log.query(f"#{panel_id}"):
            widget.remove()

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
        log.mount(panel)

    def handle_stream_started(self, log: MessageLog, event: StreamStarted) -> None:
        """Replace waiting panel with streaming panel."""
        panel_id = f"panel-{event.member}"
        for widget in log.query(f"#{panel_id}"):
            widget.remove()

        panel = StreamingPanel(sender=event.member, id=panel_id)
        log.mount(panel)

    def handle_stream_delta(self, event: StreamDelta) -> None:
        """Update the streaming panel with new text."""
        panel_id = f"panel-{event.member}"
        try:
            panel = self.query_one(f"#{panel_id}", StreamingPanel)
            panel.update_content(event.full_text)
        except Exception:
            pass  # Panel may have been replaced by finalized message

    def handle_stream_finished(self, event: StreamFinished) -> None:
        """Remove the streaming panel (finalized message replaces it)."""
        panel_id = f"panel-{event.member}"
        try:
            panel = self.query_one(f"#{panel_id}")
            panel.remove()
        except Exception:
            pass
