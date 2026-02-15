"""ChatApp — main Textual application for kd chat."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.widgets import Footer, Header, Static


class ChatApp(App):
    """Council chat TUI."""

    TITLE = "kd chat"

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, base: Path, branch: str, thread_id: str) -> None:
        super().__init__()
        self.base = base
        self.branch = branch
        self.thread_id = thread_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Thread: {self.thread_id}", id="placeholder")
        yield Footer()
