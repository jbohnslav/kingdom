from __future__ import annotations

"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from pathlib import Path
import subprocess

import typer

from kingdom.plan import parse_plan_tickets
from kingdom.state import (
    ensure_run_layout,
    logs_root,
    read_json,
    resolve_current_run,
    set_current_run,
    write_json,
)
from kingdom.tmux import (
    attach_window,
    derive_server_name,
    ensure_council_layout,
    ensure_session,
    ensure_window,
    list_panes,
    list_windows,
    send_keys,
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
    base = Path.cwd()
    feature = resolve_current_run(base)
    ensure_run_layout(base, feature)

    log_path = logs_root(base, feature) / "council.jsonl"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_council_layout(server, feature)

    target = f"{feature}:council"
    panes = sorted(list_panes(server, target), key=int)
    commands = ["claude", "codex", "agent", "claude"]
    for pane, command in zip(panes, commands):
        send_keys(server, f"{target}.{pane}", command)

    attach_window(server, feature, "council")


@app.command(help="Draft or iterate the current plan.")
def plan(
    apply: bool = typer.Option(
        False, "--apply", help="Create tk tickets from plan.md."
    ),
) -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)
    plan_path = paths["plan_md"]
    if plan_path.read_text(encoding="utf-8").strip() == "":
        template = (
            f"# Plan: {feature}\n\n"
            "## Goal\n"
            "<short goal>\n\n"
            "## Tickets\n"
            "- [ ] T1: <title>\n"
            "  - Priority: 2\n"
            "  - Depends on: <none|ticket ids>\n"
            "  - Description: ...\n"
            "  - Acceptance:\n"
            "    - [ ] ...\n\n"
            "## Revisions\n"
            "(append-only after dev starts)\n"
        )
        plan_path.write_text(template, encoding="utf-8")
        typer.echo(f"Created plan template at {plan_path}")
        return

    if not apply:
        typer.echo(f"Plan already exists at {plan_path}")
        typer.echo("Use --apply to create tk tickets from the plan.")
        return

    tickets = parse_plan_tickets(plan_path.read_text(encoding="utf-8"))
    if not tickets:
        raise RuntimeError("No tickets found in plan.md")

    created: dict[str, str] = {}
    for ticket in tickets:
        args = [
            "tk",
            "create",
            ticket["title"],
            "-p",
            str(ticket["priority"]),
        ]
        if ticket["description"]:
            args.extend(["-d", ticket["description"]])
        acceptance = "\n".join(ticket["acceptance"]).strip()
        if acceptance:
            args.extend(["--acceptance", acceptance])

        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "tk create failed")

        ticket_id = result.stdout.strip()
        created[ticket["plan_id"]] = ticket_id
        typer.echo(f"Created ticket {ticket_id} for {ticket['plan_id']}")

    for ticket in tickets:
        ticket_id = created.get(ticket["plan_id"])
        for dep in ticket["depends_on"]:
            dep_id = created.get(dep, dep)
            result = subprocess.run(["tk", "dep", ticket_id, dep_id], text=True)
            if result.returncode != 0:
                raise RuntimeError(f"tk dep failed for {ticket_id} -> {dep_id}")

    state = read_json(paths["state_json"])
    state["tickets"] = {**state.get("tickets", {}), **created}
    write_json(paths["state_json"], state)


@app.command(help="Start a Peasant for the given ticket.")
def peasant(ticket: str = typer.Argument(..., help="Ticket id to execute.")) -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)
    ensure_feature_branch(feature)

    worktrees_root = paths["state_root"] / "worktrees" / feature
    worktree_path = worktrees_root / "peasant-1"
    worktrees_root.mkdir(parents=True, exist_ok=True)

    if not worktree_path.exists():
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), feature],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git worktree add failed")

    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_window(server, feature, "peasant-1", cwd=worktree_path)
    send_keys(server, f"{feature}:peasant-1", "codex")

    state = read_json(paths["state_json"])
    state["peasant"] = {"ticket": ticket, "worktree": str(worktree_path)}
    write_json(paths["state_json"], state)


@app.command(help="Reserved for broader develop phase (MVP stub).")
def dev(ticket: str | None = typer.Argument(None, help="Optional ticket id.")) -> None:
    if ticket:
        typer.echo("MVP uses `kd peasant <ticket>` for single-ticket execution.")
        raise typer.Exit(code=1)
    typer.echo("`kd dev` is reserved. Use `kd peasant <ticket>` in the MVP.")


@app.command(help="Show current phase, run, and ticket status.")
def status() -> None:
    base = Path.cwd()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    paths = ensure_run_layout(base, feature)
    state = read_json(paths["state_json"])
    typer.echo(f"Run: {feature}")
    if state:
        typer.echo(f"State: {state}")

    server = derive_server_name(base)
    try:
        windows = list_windows(server, feature)
        typer.echo(f"Tmux windows: {', '.join(windows) if windows else 'none'}")
    except RuntimeError as exc:
        typer.echo(f"Tmux: {exc}")

    tickets = state.get("tickets", {})
    if tickets:
        typer.echo("Tickets:")
        for plan_id, ticket_id in tickets.items():
            typer.echo(f"  {plan_id} -> {ticket_id}")


@app.command(help="Attach to hand/council/peasant windows.")
def attach(target: str = typer.Argument(..., help="Target window name.")) -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    server = derive_server_name(base)
    ensure_session(server, feature)

    windows = list_windows(server, feature)
    if target not in windows:
        typer.echo(
            f"Window '{target}' not found in session '{feature}'. Available: {', '.join(windows)}"
        )
        raise typer.Exit(code=1)

    attach_window(server, feature, target)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
