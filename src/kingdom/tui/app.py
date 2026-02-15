"""ChatApp — main Textual application for kd chat."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import VerticalScroll
from textual.widgets import Static, TextArea

from kingdom.agent import resolve_all_agents
from kingdom.config import load_config
from kingdom.thread import get_thread, thread_dir

from .poll import NewMessage, StreamDelta, StreamFinished, StreamStarted, ThreadPoller
from .widgets import MessagePanel, StreamingPanel


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
        """Initialize poller and start polling."""
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

        self.set_interval(0.1, self.poll_updates)

        # Focus the input area
        input_area = self.query_one("#input-area", TextArea)
        input_area.focus()

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
        """Add a finalized message panel to the log."""
        # Remove any existing streaming/waiting panel for this sender
        panel_id = f"panel-{event.sender}"
        existing = log.query(f"#{panel_id}")
        for widget in existing:
            widget.remove()

        panel = MessagePanel(
            sender=event.sender,
            body=event.body,
            id=f"msg-{event.sequence}",
        )
        log.mount(panel)

    def handle_stream_started(self, log: MessageLog, event: StreamStarted) -> None:
        """Add a streaming panel for the member."""
        panel_id = f"panel-{event.member}"
        # Remove waiting panel if present
        existing = log.query(f"#{panel_id}")
        for widget in existing:
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
