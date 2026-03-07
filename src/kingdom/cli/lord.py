"""Lord CLI commands — orchestrates peasant workers on an epic."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from .display import print_error
from .helpers import is_process_alive, require_project_root

lord_app = typer.Typer(name="lord", help="Lord mode — orchestrate peasants on an epic.")


@lord_app.command()
def start(
    epic_id: Annotated[str, typer.Argument(help="Epic ticket ID to orchestrate.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent to use (default: from config).")] = None,
    watch: Annotated[bool, typer.Option("--watch", "-w", help="Watch lord progress after starting.")] = False,
) -> None:
    """Start the lord agent on an epic (runs on feature branch, delegates to peasant worktrees)."""
    from kingdom.config import load_config
    from kingdom.lord_harness import lord_session_name
    from kingdom.session import get_agent_state, update_agent_state
    from kingdom.state import logs_root, resolve_current_run
    from kingdom.ticket import find_ticket

    base = require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    # Resolve the epic ticket
    result = find_ticket(base, epic_id, branch=feature)
    if result is None:
        print_error(f"Ticket not found: {epic_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    full_epic_id = ticket.id

    # Must be an epic
    if ticket.type != "epic":
        print_error(f"Ticket {full_epic_id} is not an epic (type: {ticket.type}). Lord can only orchestrate epics.")
        raise typer.Exit(code=1)

    # Must not be closed
    if ticket.status == "closed":
        print_error(f"Epic {full_epic_id} is already closed.")
        raise typer.Exit(code=1)

    # Default agent from config
    if agent is None:
        cfg = load_config(base)
        agent = cfg.peasant.agent

    session_name = lord_session_name(full_epic_id)

    # Check if already running
    existing = get_agent_state(base, feature, session_name)
    if existing.status == "working" and existing.pid and is_process_alive(existing.pid):
        print_error(f"Lord already running on {full_epic_id} (pid {existing.pid})")
        raise typer.Exit(code=1)

    # Transition epic to in_progress if open
    if ticket.status == "open":
        from kingdom.ticket import write_ticket

        ticket.status = "in_progress"
        write_ticket(ticket, ticket_path)

    # Seed session state before launching
    now = datetime.now(UTC).isoformat()
    update_agent_state(
        base,
        feature,
        session_name,
        status="working",
        ticket=full_epic_id,
        agent_backend=agent,
        started_at=now,
        last_activity=now,
    )

    # Launch lord worker as background process
    pid = launch_lord_background(base, feature, full_epic_id, agent, session_name)

    # Record PID
    update_agent_state(base, feature, session_name, pid=pid)

    lord_logs_dir = logs_root(base, feature) / session_name
    typer.echo(f"Started {session_name} (pid {pid})")
    typer.echo(f"  Agent: {agent}")
    typer.echo(f"  Epic: {full_epic_id} — {ticket.title}")
    typer.echo(f"  Logs: {lord_logs_dir}")

    if watch:
        typer.echo()
        lord_watch(epic_id)


def launch_lord_background(
    base: Path,
    feature: str,
    epic_id: str,
    agent: str,
    session_name: str,
) -> int:
    """Launch the lord worker as a background process. Returns the child PID."""
    from kingdom.state import logs_root

    lord_logs_dir = logs_root(base, feature) / session_name
    lord_logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = lord_logs_dir / "stdout.log"
    stderr_log = lord_logs_dir / "stderr.log"

    work_cmd = [
        sys.executable,
        "-m",
        "kingdom.lord_worker",
        epic_id,
        "--agent",
        agent,
        "--session",
        session_name,
        "--base",
        str(base),
    ]

    stdout_fd = os.open(str(stdout_log), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    stderr_fd = os.open(str(stderr_log), os.O_WRONLY | os.O_CREAT | os.O_APPEND)

    proc = subprocess.Popen(
        work_cmd,
        stdout=stdout_fd,
        stderr=stderr_fd,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    os.close(stdout_fd)
    os.close(stderr_fd)
    return proc.pid


@lord_app.command()
def stop(
    epic_id: Annotated[
        str | None, typer.Argument(help="Epic ticket ID (optional, auto-detects if one lord running).")
    ] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Force-close session state even without a PID.")] = False,
) -> None:
    """Signal the lord agent to stop gracefully."""
    from kingdom.lord_harness import lord_session_name
    from kingdom.session import get_agent_state, list_active_agents, update_agent_state
    from kingdom.state import resolve_current_run

    base = require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    # If no epic_id given, find the running lord
    if epic_id is None:
        active = list_active_agents(base, feature)
        lords = [a for a in active if a.name.startswith("lord-") and a.status == "working"]
        if not lords:
            print_error("No running lord agent found.")
            raise typer.Exit(code=1)
        if len(lords) > 1:
            names = ", ".join(a.name for a in lords)
            print_error(f"Multiple lords running ({names}). Specify the epic ID.")
            raise typer.Exit(code=1)
        session_name = lords[0].name
        epic_id = session_name.removeprefix("lord-")
    else:
        # Resolve to full ticket ID
        from kingdom.ticket import find_ticket

        result = find_ticket(base, epic_id, branch=feature)
        if result is None:
            print_error(f"Ticket not found: {epic_id}")
            raise typer.Exit(code=1)
        epic_id = result.ticket.id
        session_name = lord_session_name(epic_id)

    state = get_agent_state(base, feature, session_name)

    if state.status not in ("working", "blocked"):
        print_error(f"Lord {epic_id} is not running (status: {state.status})")
        raise typer.Exit(code=1)

    if state.pid:
        try:
            os.killpg(state.pid, signal.SIGTERM)
            typer.echo(f"Sent SIGTERM to lord process group (pgid {state.pid})")
        except OSError:
            typer.echo(f"Lord process group {state.pid} not found (already dead)")
            if not force:
                print_error("Use --force to close session state anyway.")
                raise typer.Exit(code=1) from None
    elif not force:
        print_error(f"No PID found for lord {epic_id}. Use --force to close session state anyway.")
        raise typer.Exit(code=1)
    else:
        typer.echo(f"Lord {epic_id}: no PID found, force-closing session state")

    now = datetime.now(UTC).isoformat()
    if force and not state.pid:
        # Force mode with no process — go straight to stopped
        update_agent_state(base, feature, session_name, status="stopped", last_activity=now)
        typer.echo("Lord status updated to stopped")
    else:
        # Set to stopping — the harness will detect this and shut down gracefully,
        # then set the final "stopped" status itself
        update_agent_state(base, feature, session_name, status="stopping", last_activity=now)
        typer.echo("Lord status updated to stopping (harness will shut down gracefully)")


@lord_app.command()
def status(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Show lord agent status."""
    from kingdom.session import list_active_agents
    from kingdom.state import resolve_current_run

    base = require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    active = list_active_agents(base, feature)
    lords = [a for a in active if a.name.startswith("lord-")]

    if output_json:
        data = []
        for lord in lords:
            epic_id = lord.name.removeprefix("lord-")
            data.append(
                {
                    "epic_id": epic_id,
                    "status": lord.status,
                    "pid": lord.pid,
                    "started_at": lord.started_at,
                    "last_activity": lord.last_activity,
                    "agent": lord.agent_backend,
                }
            )
        typer.echo(json.dumps(data, indent=2))
        return

    if not lords:
        typer.echo("No lord agents active. Start one with `kd lord start <epic-id>`.")
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Lord Agents")
    table.add_column("Epic", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Agent")
    table.add_column("PID")

    for lord in lords:
        epic_id = lord.name.removeprefix("lord-")
        effective_status = lord.status
        if lord.status == "working" and (not lord.pid or not is_process_alive(lord.pid)):
            effective_status = "dead"

        status_style = {
            "working": "green",
            "blocked": "yellow",
            "done": "blue",
            "failed": "red",
            "stopped": "dim",
            "dead": "red",
        }.get(effective_status, "")

        table.add_row(
            epic_id,
            f"[{status_style}]{effective_status}[/{status_style}]" if status_style else effective_status,
            lord.agent_backend or "?",
            str(lord.pid) if lord.pid else "",
        )

    console.print(table)


@lord_app.command("watch", help="Watch lord progress in real time.")
def lord_watch(
    epic_id: Annotated[str, typer.Argument(help="Epic ticket ID.")],
    show_all: Annotated[bool, typer.Option("--all", help="Show all worklog entries (unfiltered).")] = False,
) -> None:
    """Tail the epic worklog and show lord progress."""
    import time as time_mod

    from rich.console import Console

    from kingdom.harness import extract_worklog
    from kingdom.lord_harness import lord_session_name
    from kingdom.session import get_agent_state
    from kingdom.state import resolve_current_run
    from kingdom.ticket import filter_worklog_lines, find_ticket

    base = require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    result = find_ticket(base, epic_id, branch=feature)
    if result is None:
        print_error(f"Ticket not found: {epic_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    full_epic_id = ticket.id
    session_name = lord_session_name(full_epic_id)

    console = Console()
    console.print(f"[bold]Watching {session_name}[/bold]  (Ctrl+C to stop)\n")

    TERMINAL_STATUSES = {"done", "failed", "stopped", "blocked"}
    shown_lines = 0

    def get_worklog_lines() -> list[str]:
        worklog = extract_worklog(ticket_path)
        if not worklog.strip():
            return []
        raw_lines = worklog.strip().splitlines()
        return filter_worklog_lines(raw_lines, show_all=show_all)

    try:
        while True:
            lines = get_worklog_lines()
            if len(lines) > shown_lines:
                for line in lines[shown_lines:]:
                    console.print(line, markup=False)
                shown_lines = len(lines)

            state = get_agent_state(base, feature, session_name)
            if state.status in TERMINAL_STATUSES:
                # Flush remaining
                lines = get_worklog_lines()
                if len(lines) > shown_lines:
                    for line in lines[shown_lines:]:
                        console.print(line, markup=False)

                console.print()
                console.print("=" * 40, markup=False)
                console.print(f"{state.status.upper()}: {full_epic_id}", markup=False)
                console.print("=" * 40, markup=False)
                break

            time_mod.sleep(2)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")
