"""Cross-cutting display utilities for the Kingdom CLI."""

from __future__ import annotations

import os

import typer
from rich.console import Console

error_console = Console(stderr=True)

NO_COLOR = "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"


def styled_echo(message: str, *, fg: str | None = None, err: bool = False) -> None:
    """typer.secho wrapper that respects NO_COLOR and TERM=dumb."""
    import kingdom.cli as _cli

    typer.secho(message, fg=None if _cli.NO_COLOR else fg, err=err)


def print_error(message: str) -> None:
    """Print a consistently styled error message to stderr."""
    error_console.print(f"[bold red]Error:[/bold red] {message}")


def console_width() -> int:
    """Get the current terminal width, defaulting to 120 if unavailable."""
    try:
        return os.get_terminal_size().columns
    except (ValueError, OSError):
        return 120


STATUS_STYLES = {
    "open": "green",
    "in_progress": "yellow",
    "in_review": "magenta",
    "closed": "dim",
}

STATUS_COLORS = {"open": "yellow", "in_progress": "cyan", "in_review": "magenta", "closed": "green"}
