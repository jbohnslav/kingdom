from __future__ import annotations

"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from pathlib import Path
import subprocess

import typer

from kingdom.state import ensure_run_layout, logs_root, resolve_current_run, set_current_run
from kingdom.tmux import (
    attach_window,
    derive_server_name,
    ensure_session,
    ensure_window,
)

app = typer.Typer(
    name="kd",
    help="Kingdom CLI.",
    add_completion=False,
)


def not_implemented(command: str) -> None:
    typer.echo(f"{command}: not implemented yet.")
    raise typer.Exit(code=1)


def ensure_feature_branch(feature: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to read git branch")

    current = result.stdout.strip()
    if current == feature:
        return

    if current in {"main", "master"}:
        checkout = subprocess.run(["git", "checkout", "-b", feature], text=True)
        if checkout.returncode != 0:
            raise RuntimeError(f"Failed to create branch '{feature}'")
        typer.echo(f"Created branch: {feature}")
        return

    typer.echo(
        f"Warning: current branch '{current}' does not match feature '{feature}'."
    )


@app.command(help="Initialize a run, state, and tmux session.")
def start(feature: str = typer.Argument(..., help="Feature name for the run.")) -> None:
    base = Path.cwd()
    paths = ensure_run_layout(base, feature)
    set_current_run(base, feature)
    ensure_feature_branch(feature)
    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_window(server, feature, "hand")
    typer.echo(f"Initialized run: {paths['run_root']}")
    typer.echo(f"Tmux: server={server} session={feature} window=hand")


@app.command(help="Attach to the Hand (persistent chat window).")
def chat() -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    ensure_run_layout(base, feature)

    log_path = logs_root(base, feature) / "hand.jsonl"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_window(server, feature, "hand")
    attach_window(server, feature, "hand")


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
