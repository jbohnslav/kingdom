from __future__ import annotations

"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from pathlib import Path

import typer

from kingdom.state import ensure_run_layout, set_current_run

app = typer.Typer(
    name="kd",
    help="Kingdom CLI.",
    add_completion=False,
)


def not_implemented(command: str) -> None:
    typer.echo(f"{command}: not implemented yet.")
    raise typer.Exit(code=1)


@app.command(help="Initialize a run, state, and tmux session.")
def start(feature: str = typer.Argument(..., help="Feature name for the run.")) -> None:
    base = Path.cwd()
    paths = ensure_run_layout(base, feature)
    set_current_run(base, feature)
    typer.echo(f"Initialized run: {paths['run_root']}")


@app.command(help="Attach to the Hand (persistent chat window).")
def chat() -> None:
    not_implemented("kd chat")


@app.command(help="Open council panes for claude/codex/agent plus synthesis.")
def council() -> None:
    not_implemented("kd council")


@app.command(help="Draft or iterate the current plan.")
def plan() -> None:
    not_implemented("kd plan")


@app.command(help="Start a Peasant for the given ticket.")
def peasant(ticket: str = typer.Argument(..., help="Ticket id to execute.")) -> None:
    not_implemented("kd peasant")


@app.command(help="Reserved for broader develop phase (MVP stub).")
def dev(ticket: str | None = typer.Argument(None, help="Optional ticket id.")) -> None:
    not_implemented("kd dev")


@app.command(help="Show current phase, run, and ticket status.")
def status() -> None:
    not_implemented("kd status")


@app.command(help="Attach to hand/council/peasant windows.")
def attach(target: str = typer.Argument(..., help="Target window name.")) -> None:
    not_implemented("kd attach")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
