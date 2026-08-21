"""Peasant CLI commands."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NamedTuple

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from kingdom.parsing import parse_iso_datetime
from kingdom.state import (
    backlog_root,
    branch_root,
    branches_root,
    clear_terminal_ticket_contexts,
    clear_ticket_execution_contexts,
    find_git_root,
    flock,
    get_current_git_branch,
    logs_root,
    normalize_branch_name,
    read_json,
    resolve_current_run,
    ticket_assignment_lock_path,
)
from kingdom.ticket import (
    Ticket,
    blocking_dependencies,
    move_ticket,
    read_ticket,
    resolve_ticket_dependencies,
    write_ticket,
)
from kingdom.worktree import (
    check_uncommitted_changes,
    create_worktree,
    existing_worktree_path_for,
    remove_worktree,
    run_init_script,
)

from .display import error_console, print_error, styled_echo
from .helpers import (
    is_process_alive,
    peasant_session_name,
    peasant_thread_id,
    require_project_root,
    resolve_ticket_or_exit,
    verbose_echo,
)

peasant_app = typer.Typer(name="peasant", help="Manage peasant agents.")

PEASANT_LOCK_TIMEOUT_SECONDS = 30.0


class PeasantContext(NamedTuple):
    """Resolved ticket and (optionally) feature branch for a peasant command."""

    base: Path
    ticket: Ticket
    ticket_path: Path
    full_ticket_id: str
    feature: str
    git_root: Path


def resolve_invocation_git_root(base: Path) -> Path:
    """Return the checkout git commands should operate on.

    When ``kd`` is invoked under the Kingdom project root, use that root even if
    a nested repo or submodule is closer to cwd. When ``base`` points at a
    sibling checkout that owns ``.kd/``, fall back to git discovery for the
    invocation worktree.
    """
    cwd = Path.cwd().resolve()
    base = base.resolve()

    if cwd == base or base in cwd.parents:
        return base

    current = cwd
    while True:
        if (current / ".git").exists():
            return current
        if current == base:
            return base
        if current.parent == current:
            break
        current = current.parent

    return find_git_root(cwd) or base


def resolve_peasant_context(ticket_id: str, base: Path | None = None, auto_pull: bool = False) -> PeasantContext:
    """Resolve ticket and feature branch, or exit with an error message.

    For post-start commands (auto_pull=False), searches all branches for
    the peasant's session so that cross-branch operations work regardless
    of which session is currently active.

    For mutating commands (auto_pull=True, i.e. peasant start), uses the
    current session as before.

    Args:
        auto_pull: If True, move backlog tickets into the current branch.
            Only set for mutating commands (peasant start).
    """
    from kingdom.session import find_peasant_branch

    base = base or require_project_root()
    git_root = resolve_invocation_git_root(base)

    # For non-start commands, try to find the peasant's owning branch first.
    # Resolve the full ticket ID before building the session name — the user
    # may pass a prefix (e.g. "0e") but session files use the full ID.
    if not auto_pull:
        ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
        session_name = f"peasant-{ticket.id}"
        owning_branch = find_peasant_branch(base, session_name)
        if owning_branch:
            return PeasantContext(
                base=base,
                ticket=ticket,
                ticket_path=ticket_path,
                full_ticket_id=ticket.id,
                feature=owning_branch,
                git_root=git_root,
            )

    # Fall back to current session (required for start, fine for others)
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id, branch=feature)
    full_ticket_id = ticket.id

    # Auto-pull backlog tickets into the current branch (mutating commands only)
    if auto_pull and ticket_path.parent == backlog_root(base) / "tickets":
        ticket_path = move_ticket(ticket_path, branch_root(base, feature) / "tickets")

    return PeasantContext(
        base=base,
        ticket=ticket,
        ticket_path=ticket_path,
        full_ticket_id=full_ticket_id,
        feature=feature,
        git_root=git_root,
    )


def launch_work_background(
    base: Path,
    feature: str,
    ticket_id: str,
    agent: str,
    worktree_path: Path,
    thread_id: str,
    session_name: str,
) -> int:
    """Launch the worker as a background process.

    Builds the command, opens log file descriptors, spawns via Popen, and
    returns the child PID.  Used by ``peasant start`` and ``peasant reject``.
    """
    peasant_logs_dir = logs_root(base, feature) / session_name
    peasant_logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = peasant_logs_dir / "stdout.log"
    stderr_log = peasant_logs_dir / "stderr.log"

    work_cmd = [
        sys.executable,
        "-m",
        "kingdom.worker",
        ticket_id,
        "--agent",
        agent,
        "--worktree",
        str(worktree_path),
        "--thread",
        thread_id,
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


def launch_work_tmux(
    base: Path,
    feature: str,
    ticket_id: str,
    agent: str,
    worktree_path: Path,
    thread_id: str,
    session_name: str,
) -> int:
    """Launch the worker in a new tmux window.

    Errors if tmux is not running. Returns the PID of the tmux
    new-window shell (the agent process runs inside it).
    """
    # Check tmux is running
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print_error("tmux is not running. Start tmux first or omit --tmux.")
            raise typer.Exit(code=1)
    except FileNotFoundError:
        print_error("tmux is not installed.")
        raise typer.Exit(code=1) from None

    work_cmd = " ".join(
        [
            shlex.quote(sys.executable),
            "-m",
            "kingdom.worker",
            shlex.quote(ticket_id),
            "--agent",
            shlex.quote(agent),
            "--worktree",
            shlex.quote(str(worktree_path)),
            "--thread",
            shlex.quote(thread_id),
            "--session",
            shlex.quote(session_name),
            "--base",
            shlex.quote(str(base)),
        ]
    )

    window_name = peasant_session_name(ticket_id)
    tmux_cmd = [
        "tmux",
        "new-window",
        "-n",
        window_name,
        "-P",  # print window info
        work_cmd,
    ]

    proc = subprocess.run(tmux_cmd, capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        print_error(f"failed to create tmux window: {proc.stderr.strip()}")
        raise typer.Exit(code=1)

    # Get the PID of the shell running in the new window
    # tmux new-window -P prints something like "main:2.0"
    # We'll use tmux list-panes to find the PID
    pane_target = proc.stdout.strip()
    try:
        pid_result = subprocess.run(
            ["tmux", "list-panes", "-t", pane_target, "-F", "#{pane_pid}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pid = int(pid_result.stdout.strip().splitlines()[0])
    except (ValueError, IndexError, subprocess.TimeoutExpired) as exc:
        print_error(
            f"tmux window created but PID discovery failed: {exc}\n"
            "  The agent may be running in tmux but cannot be tracked.\n"
            "  Use `tmux list-windows` to find it, or retry with `--hand`."
        )
        raise typer.Exit(code=1) from None

    return pid


@peasant_app.command("start", help="Launch a peasant agent on a ticket.")
def peasant_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID to work on.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent to use (default: from config).")] = None,
    hand: Annotated[bool, typer.Option("--hand", help="Run in current directory (serial mode).")] = False,
    tmux: Annotated[bool, typer.Option("--tmux", help="Open agent in a new tmux window.")] = False,
    watch: Annotated[bool, typer.Option("--watch", "-w", help="Watch peasant progress after starting.")] = False,
    no_preflight: Annotated[bool, typer.Option("--no-preflight", help="Skip uncommitted-changes warning.")] = False,
) -> None:
    """Create worktree, session, thread, and launch agent harness in background."""
    ctx = resolve_peasant_context(ticket_id, auto_pull=True)
    start_peasant(ctx, agent=agent, hand=hand, tmux=tmux, no_preflight=no_preflight)

    if watch:
        typer.echo()
        peasant_watch(ticket_id)


def start_peasant(
    ctx: PeasantContext,
    *,
    agent: str | None,
    hand: bool,
    tmux: bool,
    no_preflight: bool,
) -> None:
    """Launch one peasant after serializing starts for its ticket."""
    lock_path = ctx.ticket_path.parent / f".{ctx.ticket_path.name}.start.lock"
    try:
        with flock(lock_path, timeout_seconds=PEASANT_LOCK_TIMEOUT_SECONDS):
            fresh_ctx = ctx._replace(ticket=read_ticket(ctx.ticket_path))
            launch_peasant(fresh_ctx, agent=agent, hand=hand, tmux=tmux, no_preflight=no_preflight)
    except TimeoutError:
        print_error(f"Another start for {ctx.full_ticket_id} is still running. Retry shortly.")
        raise typer.Exit(code=1) from None


def launch_peasant(
    ctx: PeasantContext,
    *,
    agent: str | None,
    hand: bool,
    tmux: bool,
    no_preflight: bool,
) -> None:
    """Create one peasant's worktree, session, thread, and worker process."""
    import kingdom.cli as _cli
    from kingdom.config import load_config
    from kingdom.session import update_agent_state
    from kingdom.thread import create_thread

    base, ticket, full_ticket_id, feature = ctx.base, ctx.ticket, ctx.full_ticket_id, ctx.feature

    # Block starting work on tickets that are in_review or closed
    if ticket.status in ("in_review", "closed"):
        print_error(f"Cannot start work on {full_ticket_id}: ticket is {ticket.status}")
        raise typer.Exit(code=1)

    # Block starting work on epic tickets (epics aren't atomic work units)
    if ticket.type == "epic":
        print_error(
            f"Cannot start a peasant on {full_ticket_id}: epic tickets are not atomic work units. Break it into child tickets first."
        )
        raise typer.Exit(code=1)

    blockers = blocking_dependencies(resolve_ticket_dependencies(base, ticket))
    if blockers:
        details = ", ".join(f"{dep} ({status})" for dep, status in blockers)
        print_error(f"Cannot start work on {full_ticket_id}: blocked by {details}")
        raise typer.Exit(code=1)

    # Default agent from config if not specified on CLI
    if agent is None:
        cfg = load_config(base)
        agent = cfg.peasant.agent

    session_name = peasant_session_name(full_ticket_id)
    thread_id = peasant_thread_id(full_ticket_id)

    # Check if already running
    from kingdom.session import get_agent_state

    existing = get_agent_state(base, feature, session_name)
    if existing.status == "working" and existing.pid and is_process_alive(existing.pid):
        print_error(f"Peasant already running on {full_ticket_id} (pid {existing.pid})")
        raise typer.Exit(code=1)

    # 0. Preflight: warn on uncommitted changes (skipped in hand mode or with --no-preflight)
    if not hand and not no_preflight:
        uncommitted = check_uncommitted_changes(ctx.git_root, ignore_kd=True)
        if uncommitted:
            error_console.print(
                f"[yellow]Warning:[/yellow] {len(uncommitted)} uncommitted change(s) in {ctx.git_root}.\n"
                "  Worktrees are created from the last commit — uncommitted changes won't be included.\n"
                "  Commit or stash first, or use [bold]--hand[/bold] to work in the current directory."
            )

    # 1. Create worktree (or use base if hand mode)
    if hand:
        # Guard: block if another peasant is already running on the same checkout
        from kingdom.session import list_active_agents

        for active in list_active_agents(base, feature):
            if active.name == session_name:
                continue  # already handled above
            if (
                active.status == "working"
                and active.pid
                and active.name.startswith("peasant-")
                and is_process_alive(active.pid)
            ):
                print_error(
                    f"peasant {active.name} (pid {active.pid}) is already working "
                    f"on this checkout. Stop it first or use worktree mode."
                )
                raise typer.Exit(code=1)
        worktree_path = ctx.git_root
        typer.echo(f"Running in hand mode (serial) on {ctx.git_root}")
    else:
        try:
            worktree_path = create_worktree(base, full_ticket_id, log=typer.echo, git_root=ctx.git_root)
        except RuntimeError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from None

    # Auto-assign only after slow setup, with a fresh eligibility check so a
    # native owner that started while the worktree was created wins cleanly.
    with flock(ticket_assignment_lock_path(base)):
        ticket = read_ticket(ctx.ticket_path)
        if ticket.status in ("in_review", "closed"):
            print_error(f"Cannot start work on {full_ticket_id}: ticket is {ticket.status}")
            raise typer.Exit(code=1)
        if ticket.status == "in_progress" and ticket.assignee not in (None, "hand", session_name):
            print_error(f"Cannot start work on {full_ticket_id}: ticket is owned by {ticket.assignee}")
            raise typer.Exit(code=1)
        if ticket.status == "open":
            ticket.status = "in_progress"
        ticket.assignee = session_name
        write_ticket(ticket, ctx.ticket_path)
        clear_ticket_execution_contexts(base, ticket.id)
        clear_terminal_ticket_contexts(base, ticket.id)

    # 2. Create work thread (ignore if already exists)
    with contextlib.suppress(FileExistsError):
        create_thread(base, feature, thread_id, [session_name, "king"], "work")

    # 3. Seed thread with ticket_start message
    from kingdom.thread import add_message, thread_dir

    tdir = thread_dir(base, feature, thread_id)
    # Only seed if no messages yet
    existing_msgs = list(tdir.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not existing_msgs:
        seed_body = f"# Starting work on {full_ticket_id}\n\n"
        seed_body += f"**Title:** {ticket.title}\n\n"
        seed_body += ticket.body
        add_message(base, feature, thread_id, from_="king", to=session_name, body=seed_body)

    # 4. Seed session state BEFORE launching the worker process.
    # The worker reads session state immediately on startup (e.g. hand_mode for
    # branch validation), so it must be initialized before the process exists.
    now = datetime.now(UTC).isoformat()
    session_fields = {
        "status": "working",
        "ticket": full_ticket_id,
        "thread": thread_id,
        "agent_backend": agent,
        "started_at": now,
        "last_activity": now,
        "hand_mode": hand,
    }
    if existing.resume_id and existing.agent_backend and existing.agent_backend != agent:
        session_fields["resume_id"] = None
    update_agent_state(base, feature, session_name, **session_fields)

    # 5. Launch harness
    try:
        if tmux:
            pid = launch_work_tmux(base, feature, full_ticket_id, agent, worktree_path, thread_id, session_name)
        else:
            pid = _cli.launch_work_background(
                base, feature, full_ticket_id, agent, worktree_path, thread_id, session_name
            )
    except Exception as exc:
        # Launch failed — don't leave a phantom "working" session behind
        update_agent_state(base, feature, session_name, status="failed", last_activity=datetime.now(UTC).isoformat())
        print_error(f"Failed to launch worker: {exc}")
        raise typer.Exit(code=1) from None

    # 6. Record pid only — don't re-write status, so a fast worker failure isn't clobbered
    update_agent_state(base, feature, session_name, pid=pid)

    peasant_logs_dir = logs_root(base, feature) / session_name
    mode = "tmux" if tmux else "background"
    typer.echo(f"Started {session_name} (pid {pid}, {mode})")
    typer.echo(f"  Agent: {agent}")
    typer.echo(f"  Ticket: {full_ticket_id}")
    typer.echo(f"  Worktree: {worktree_path}")
    typer.echo(f"  Thread: {thread_id}")
    typer.echo(f"  Logs: {peasant_logs_dir}")
    verbose_echo(f"ticket path: {ctx.ticket_path}")
    verbose_echo(f"thread dir: {tdir}")
    verbose_echo(f"hand mode: {hand}")


TERMINAL_STATUSES = {"done", "failed", "stopped"}
WATCH_TERMINAL_STATUSES = {"done", "failed", "stopped", "needs_king_review", "blocked"}


@peasant_app.command("status", help="Show active peasants.")
def peasant_status(
    show_all: Annotated[bool, typer.Option("--all", "-a", help="Include completed/stopped peasants.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Show table of active peasants: ticket, agent, status, elapsed, last activity."""

    from kingdom.session import list_active_agents

    base = require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    console = Console()
    active = list_active_agents(base, feature)

    # Filter to peasant sessions only
    peasants = [a for a in active if a.name.startswith("peasant-")]

    # By default, hide terminal sessions
    hidden: list = []
    if not show_all:
        all_peasants = peasants
        peasants = [p for p in peasants if p.status not in TERMINAL_STATUSES]
        hidden = [p for p in all_peasants if p.status in TERMINAL_STATUSES]

    now = datetime.now(UTC)

    def peasant_to_dict(p):
        ticket = p.ticket or p.name.replace("peasant-", "")
        last_dt = None
        if p.last_activity:
            with contextlib.suppress(ValueError, TypeError):
                last_dt = parse_iso_datetime(p.last_activity)

        elapsed_minutes = None
        if p.started_at:
            try:
                started = parse_iso_datetime(p.started_at)
                elapsed_at = last_dt if p.status in TERMINAL_STATUSES and last_dt else now
                elapsed_minutes = int((elapsed_at - started).total_seconds() / 60)
            except (ValueError, TypeError):
                pass
        last_activity_minutes = None
        if last_dt:
            last_activity_minutes = int((now - last_dt).total_seconds() / 60)
        # Effective status: report "dead" not "working" for dead processes
        effective_status = p.status
        if p.status == "working" and (not p.pid or not is_process_alive(p.pid)):
            effective_status = "dead"
        return {
            "ticket": ticket,
            "agent": p.agent_backend or None,
            "status": effective_status,
            "failure_kind": p.failure_kind,
            "elapsed_minutes": elapsed_minutes,
            "last_activity_minutes": last_activity_minutes,
            "pid": p.pid,
            "started_at": p.started_at,
            "last_activity": p.last_activity,
        }

    if output_json:
        data = [peasant_to_dict(p) for p in peasants]
        typer.echo(json.dumps(data, indent=2))
        return

    if not peasants:
        if hidden:
            from collections import Counter

            counts = Counter(p.status for p in hidden)
            parts = [f"{n} {s}" for s, n in sorted(counts.items())]
            summary = ", ".join(parts)
            typer.echo(f"No active peasants ({summary} — use --all to show).")
        else:
            typer.echo("No active peasants. Start one with `kd peasant start <ticket-id>`.")
        return

    table = Table(title="Active Peasants")
    table.add_column("Ticket", style="cyan")
    table.add_column("Agent")
    table.add_column("Status", style="bold")
    table.add_column("Elapsed")
    table.add_column("Last Activity")

    for p in peasants:
        d = peasant_to_dict(p)

        # Color status
        status_style = {
            "working": "green",
            "blocked": "yellow",
            "done": "blue",
            "failed": "red",
            "stopped": "dim",
            "dead": "red",
            "awaiting_council": "magenta",
            "needs_king_review": "cyan",
        }.get(d["status"], "")
        status_label = d["status"]
        if d["failure_kind"]:
            status_label += f"/{d['failure_kind']}"

        elapsed = f"{d['elapsed_minutes']}m" if d["elapsed_minutes"] is not None else ""
        last = f"{d['last_activity_minutes']}m ago" if d["last_activity_minutes"] is not None else ""

        table.add_row(
            d["ticket"],
            d["agent"] or "?",
            f"[{status_style}]{status_label}[/{status_style}]" if status_style else status_label,
            elapsed,
            last,
        )

    console.print(table)
    if hidden:
        from collections import Counter

        counts = Counter(p.status for p in hidden)
        parts = [f"{n} {s}" for s, n in sorted(counts.items())]
        summary = ", ".join(parts)
        console.print(f"[dim]{summary} — use --all to show[/dim]")


@peasant_app.command("show", help="Show structured peasant history.")
def peasant_show(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Show worklog, agent activity, and commits for a peasant."""
    from kingdom.harness import extract_worklog
    from kingdom.session import get_agent_state

    ctx = resolve_peasant_context(ticket_id)
    session_name = peasant_session_name(ctx.full_ticket_id)
    console = Console()
    state = get_agent_state(ctx.base, ctx.feature, session_name)

    # --- Worklog ---
    worklog = extract_worklog(ctx.ticket_path)

    # --- Agent activity from agent-live.log ---
    agent_live_log = logs_root(ctx.base, ctx.feature) / session_name / "agent-live.log"
    activity: list[str] = []
    if agent_live_log.exists() and agent_live_log.stat().st_size > 0:
        # Resolve backend for NDJSON decoding
        agent_backend = ""
        try:
            from kingdom.config import load_config

            cfg = load_config(ctx.base)
            agent_name = state.agent_backend or "claude"
            agent_def = cfg.agents.get(agent_name)
            if agent_def:
                agent_backend = agent_def.backend
        except Exception:
            pass

        raw_lines = agent_live_log.read_text(encoding="utf-8", errors="replace").splitlines()

        # Reassemble NDJSON stream text (flush=True since we're reading after the fact)
        stream_lines, _ = reassemble_stream_text(
            "",
            raw_lines,
            agent_backend,
            max_lines=500,
            max_chars=300,
            flush=True,
        )
        # Also pick up non-NDJSON readable lines
        plain_lines = filter_agent_log_lines(raw_lines, max_lines=500, max_chars=300)

        # Plain lines are non-JSON human-readable output; stream lines are
        # reassembled NDJSON text fragments.  We concatenate them (plain first)
        # because they come from the same log file but are extracted by
        # different parsers — ordering within each group is chronological.
        activity = plain_lines + stream_lines

    # --- Commits on the peasant's branch ---
    branch_name = f"ticket/{ctx.full_ticket_id}"
    if state.hand_mode:
        start_sha = state.start_sha
        log_spec = [f"{start_sha}..HEAD"] if start_sha else ["HEAD"]
    else:
        # ctx.feature may be normalized (slashes→dashes); resolve the
        # original git branch name from state.json for a valid ref.
        st = read_json(branch_root(ctx.base, ctx.feature) / "state.json")
        git_ref = st.get("branch")
        if not git_ref:
            current_git_branch = get_current_git_branch(ctx.git_root)
            if current_git_branch and normalize_branch_name(current_git_branch) == normalize_branch_name(ctx.feature):
                git_ref = current_git_branch
            else:
                git_ref = ctx.feature
        log_spec = [f"{git_ref}..{branch_name}"]
    commits: list[str] = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", *log_spec],
            capture_output=True,
            text=True,
            cwd=str(ctx.git_root),
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            commits = result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if output_json:
        data = {
            "ticket_id": ctx.full_ticket_id,
            "status": state.status,
            "agent": state.agent_backend,
            "pid": state.pid,
            "started_at": state.started_at,
            "hand_mode": state.hand_mode,
            "worklog": worklog or None,
            "activity": activity,
            "commits": commits,
        }
        typer.echo(json.dumps(data, indent=2))
        return

    # --- Rich display ---
    if worklog:
        console.print(Markdown(f"## Worklog\n\n{worklog}"))
    else:
        typer.echo("(no worklog entries)")

    if activity:
        console.print(Markdown("## Agent Activity"))
        for line in activity:
            console.print(f"  {line}", markup=False)
    elif not (agent_live_log.exists() and agent_live_log.stat().st_size > 0):
        typer.echo("(no agent activity log)")

    if commits:
        console.print(Markdown(f"## Commits\n\n```\n{chr(10).join(commits)}\n```"))
    else:
        typer.echo("(no commits)")


FLAG_VERBS: dict[str, str] = {
    "M": "Editing",
    "A": "Created",
    "D": "Deleted",
    "R": "Renamed",
    "??": "New file",
}


def filter_agent_log_lines(lines: list[str], max_lines: int = 3, max_chars: int = 200) -> list[str]:
    """Filter raw agent log lines to human-readable non-NDJSON content.

    Strips ANSI escapes, skips JSON and metadata noise, and returns the last
    *max_lines* readable plain-text lines each truncated to *max_chars*.

    NDJSON stream text is **not** handled here — use :func:`reassemble_stream_text`
    for that. This function still skips JSON lines so they don't leak as noise.
    """

    ansi_re = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    readable: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        if not line:
            continue
        cleaned = ansi_re.sub("", line)
        if not cleaned.strip():
            continue
        stripped = cleaned.strip()
        # Skip any JSON lines — NDJSON is handled by reassemble_stream_text
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                json.loads(stripped)
                continue
            except json.JSONDecodeError:
                pass
        # Skip common tool/metadata noise
        if stripped.startswith("╭") or stripped.startswith("╰") or stripped.startswith("│"):
            continue
        if len(stripped) < 3:
            continue
        truncated = stripped[:max_chars] + "..." if len(stripped) > max_chars else stripped
        readable.append(truncated)
    return readable[-max_lines:]


# Sentence-ending punctuation followed by whitespace — used to split reassembled
# stream text into display-ready lines.
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def reassemble_stream_text(
    buffer: str,
    new_lines: list[str],
    backend: str,
    max_lines: int = 3,
    max_chars: int = 200,
    min_display_len: int = 20,
    flush: bool = False,
) -> tuple[list[str], str]:
    """Accumulate NDJSON stream deltas into coherent display lines.

    Pure function. Takes the carry-over *buffer* from the previous poll,
    a batch of raw log *new_lines*, and the *backend* name. Extracts text
    from NDJSON events, appends to the buffer, splits on real boundaries
    (newlines, then sentence-ending punctuation), and returns
    ``(display_lines, remaining_buffer)``.

    Set *flush=True* when the agent has finished to emit any remaining
    buffer content regardless of length.
    """

    from kingdom.agent import extract_stream_text

    ansi_re = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

    # Extract text from NDJSON lines and append to buffer
    for raw_line in new_lines:
        line = raw_line.rstrip()
        if not line:
            continue
        cleaned = ansi_re.sub("", line).strip()
        if not cleaned:
            continue
        if not (cleaned.startswith("{") or cleaned.startswith("[")):
            continue
        # Only process valid JSON
        try:
            json.loads(cleaned)
        except (ValueError, json.JSONDecodeError):
            continue
        if not backend:
            continue
        text = extract_stream_text(cleaned, backend)
        if text:
            buffer += text

    if not buffer:
        return [], ""

    # Split buffer on newlines first — these are authoritative boundaries
    raw_segments: list[str] = buffer.splitlines(keepends=True)

    display: list[str] = []
    remaining = ""

    for segment in raw_segments:
        has_newline = segment.endswith("\n")
        stripped = segment.strip()
        if not stripped:
            continue

        if has_newline:
            # Complete line — split further on sentence boundaries
            sentences = SENTENCE_BOUNDARY_RE.split(stripped)
            for s in sentences:
                s = s.strip()
                if s:
                    display.append(s)
        else:
            # No trailing newline — this is the tail of the buffer.
            # Try to extract complete sentences from it.
            sentences = SENTENCE_BOUNDARY_RE.split(stripped)
            if len(sentences) > 1:
                # All but last are complete sentences
                for s in sentences[:-1]:
                    s = s.strip()
                    if s:
                        display.append(s)
                # Preserve trailing whitespace from original segment so
                # concatenation with next poll's text doesn't lose spaces.
                last = sentences[-1]
                trailing = segment[segment.rindex(last) + len(last) :]
                remaining = last + trailing.rstrip("\n")
            else:
                # Keep original trailing whitespace for buffer carry-over
                remaining = segment.rstrip("\n")

    # On flush, emit whatever remains regardless of length
    if flush and remaining:
        display.append(remaining)
        remaining = ""

    # Filter out short fragments and truncate
    result: list[str] = []
    for line in display:
        if len(line) < min_display_len and not flush:
            continue
        truncated = line[:max_chars] + "..." if len(line) > max_chars else line
        result.append(truncated)

    return result[-max_lines:], remaining


def poll_worktree(worktree: Path) -> list[str] | None:
    """Poll git status in a worktree, returning human-readable entries or None."""
    import subprocess

    if not worktree.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        entries = []
        for line in result.stdout.strip().splitlines():
            flag = line[:2].strip()
            path = line[3:].strip()
            verb = FLAG_VERBS.get(flag, flag)
            entries.append(f"{verb} {path}")
        return entries
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def poll_head_commit(worktree: Path) -> tuple[str, str] | None:
    """Return (short_sha, subject) for HEAD in the worktree, or None."""
    import subprocess

    if not worktree.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        line = result.stdout.strip()
        sha, _, subject = line.partition(" ")
        return (sha, subject)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def poll_council_status(base: Path, branch: str, thread_id: str) -> str | None:
    """Return live council status for a specific work thread.

    Peasant review runs inside the ticket's work thread, not a separate
    branch-level council thread. Scope the status lookup to that thread so
    stale stream files from unrelated council chats do not leak into watch.
    """
    from kingdom.thread import (
        get_thread,
        is_error_response,
        is_timeout_response,
        list_messages,
        thread_dir,
    )

    try:
        get_thread(base, branch, thread_id)
    except FileNotFoundError:
        return None

    tdir = thread_dir(base, branch, thread_id)
    stream_members = {
        path.name.removeprefix(".stream-").removesuffix(".jsonl") for path in tdir.glob(".stream-*.jsonl")
    }
    if not stream_members:
        return None

    messages = list_messages(base, branch, thread_id)
    last_ask_seq = 0
    for msg in messages:
        if msg.from_ == "king":
            last_ask_seq = msg.sequence

    response_msgs = {
        msg.from_: msg
        for msg in messages
        if msg.sequence > last_ask_seq and msg.from_ not in {"king"} and not msg.from_.startswith("peasant-")
    }
    expected = stream_members | set(response_msgs)

    parts: list[str] = []
    for name in sorted(expected):
        msg = response_msgs.get(name)
        if msg:
            if msg.status == "timeout" or is_timeout_response(msg.body):
                parts.append(f"{name} timed_out")
            elif msg.status in ("error", "interrupted") or is_error_response(msg.body):
                parts.append(f"{name} errored")
            else:
                parts.append(f"{name} responded")
        elif name in stream_members:
            parts.append(f"{name} running")
        else:
            parts.append(f"{name} pending")

    detail = ", ".join(parts) if parts else "waiting"
    return f"Awaiting council response — {detail}"


@peasant_app.command("watch", help="Watch peasant progress in real time.")
def peasant_watch(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Tail the ticket worklog and show progress as the peasant works.

    Exits on Ctrl+C or when the peasant finishes (terminal status).
    """
    import time as time_mod

    import kingdom.cli as _cli
    from kingdom.session import get_agent_state

    ctx = _cli.resolve_peasant_context(ticket_id)
    session_name = peasant_session_name(ctx.full_ticket_id)

    console = Console()
    console.print(f"[bold]Watching {session_name}[/bold]  (Ctrl+C to stop)\n")

    # Resolve worktree path for activity polling
    state = get_agent_state(ctx.base, ctx.feature, session_name)
    worktree = (
        ctx.git_root
        if state.hand_mode
        else existing_worktree_path_for(ctx.base, ctx.full_ticket_id, feature=ctx.feature)
    )

    # Resolve agent backend for NDJSON stream decoding
    agent_backend = ""
    try:
        from kingdom.config import load_config

        cfg = load_config(ctx.base)
        agent_name = state.agent_backend or "claude"
        agent_def = cfg.agents.get(agent_name)
        if agent_def:
            agent_backend = agent_def.backend
    except Exception:
        console.print("[dim]Warning: could not detect agent backend, streaming output may be limited[/dim]")

    # Track what we've already shown
    shown_lines: int = 0
    last_activity_time: float = time_mod.monotonic()
    last_worktree_poll: float = 0.0
    last_heartbeat_time: float = 0.0
    last_log_poll: float = 0.0
    worktree_poll_interval = 30.0  # seconds between worktree polls
    log_poll_interval = 15.0  # seconds between agent log polls
    stream_buffer: str = ""  # carry-over buffer for reassemble_stream_text

    # Seed worktree status so we don't re-report existing state with current time
    last_worktree_status: list[str] | None = poll_worktree(worktree)

    # Resolve agent live log path and skip to end so we don't replay old content
    agent_live_log = logs_root(ctx.base, ctx.feature) / session_name / "agent-live.log"
    try:
        agent_log_offset: int = agent_live_log.stat().st_size
    except OSError:
        agent_log_offset = 0

    # Seed HEAD SHA so we can detect commits
    head = poll_head_commit(worktree)
    last_head_sha: str | None = head[0] if head else None

    def get_worklog_lines() -> list[str]:
        """Read current worklog lines from the ticket file."""
        from kingdom.harness import extract_worklog

        worklog = extract_worklog(ctx.ticket_path)
        if not worklog.strip():
            return []
        return worklog.strip().splitlines()

    def flush_worklog() -> None:
        """Print any new worklog lines and update tracking."""
        nonlocal shown_lines, last_activity_time
        lines = get_worklog_lines()
        if len(lines) > shown_lines:
            for line in lines[shown_lines:]:
                console.print(line, markup=False)
            shown_lines = len(lines)
            last_activity_time = time_mod.monotonic()

    try:
        while True:
            now = time_mod.monotonic()
            flush_worklog()

            # Check if peasant is still running
            state = get_agent_state(ctx.base, ctx.feature, session_name)
            if state.status in WATCH_TERMINAL_STATUSES:
                flush_worklog()

                # Flush any remaining stream buffer
                if stream_buffer.strip():
                    final_lines, stream_buffer = reassemble_stream_text(stream_buffer, [], agent_backend, flush=True)
                    if final_lines:
                        ts = time_mod.strftime("%H:%M")
                        for line in final_lines:
                            console.print(f"  [{ts}] {line}", markup=False)

                # Map status to action command and display label
                status_actions = {
                    "needs_king_review": f"kd peasant review {ctx.full_ticket_id}",
                    "blocked": f"kd peasant show {ctx.full_ticket_id}",
                    "failed": f"kd peasant show {ctx.full_ticket_id}",
                    "done": None,
                    "stopped": None,
                }
                action = status_actions.get(state.status)
                label = state.status.upper().replace("_", " ")

                console.print()
                console.print("=" * 40, markup=False)
                console.print(f"{label}: {ctx.full_ticket_id}", markup=False)
                if action:
                    console.print(f"  {action}", markup=False)
                console.print("=" * 40, markup=False)
                break

            # Worktree activity polling between worklog entries
            if now - last_worktree_poll >= worktree_poll_interval:
                last_worktree_poll = now
                wt_status = poll_worktree(worktree)
                if wt_status and wt_status != last_worktree_status:
                    ts = time_mod.strftime("%H:%M")
                    for entry in wt_status:
                        console.print(f"  [{ts}] {entry}", markup=False)
                    last_worktree_status = wt_status
                    last_activity_time = now
                elif not wt_status and last_worktree_status:
                    # Dirty→clean transition: check if HEAD changed
                    head = poll_head_commit(worktree)
                    ts = time_mod.strftime("%H:%M")
                    if head and head[0] != last_head_sha:
                        last_head_sha = head[0]
                        console.print(
                            f'  [{ts}] Committed {head[0]} "{head[1]}"',
                            markup=False,
                        )
                    else:
                        console.print(f"  [{ts}] Changes cleared", markup=False)
                    last_worktree_status = None
                    last_activity_time = now

            # Agent live log tailing — shows what the agent is doing between worklogs
            if now - last_log_poll >= log_poll_interval and agent_live_log.exists():
                last_log_poll = now
                try:
                    file_size = agent_live_log.stat().st_size
                    if file_size > agent_log_offset:
                        with agent_live_log.open("r", encoding="utf-8", errors="replace") as f:
                            f.seek(agent_log_offset)
                            new_content = f.read()
                        agent_log_offset = file_size
                        new_lines = new_content.splitlines()
                        # Reassemble NDJSON stream deltas into coherent lines
                        stream_lines, stream_buffer = reassemble_stream_text(stream_buffer, new_lines, agent_backend)
                        # Also pick up any non-NDJSON readable lines
                        plain_lines = filter_agent_log_lines(new_lines)
                        readable = plain_lines + stream_lines
                        if readable:
                            ts = time_mod.strftime("%H:%M")
                            for line in readable:
                                console.print(f"  [{ts}] {line}", markup=False)
                            last_activity_time = now
                except OSError:
                    pass

            # Heartbeat: if no activity for 60s, show status
            silence = now - last_activity_time
            if silence >= 60 and now - last_heartbeat_time >= 60:
                last_heartbeat_time = now
                council_status = poll_council_status(ctx.base, ctx.feature, f"{ctx.full_ticket_id}-work")
                if council_status:
                    console.print(f"  [dim]{council_status}[/dim]")
                else:
                    elapsed_mins = int(silence / 60)
                    console.print(f"  [dim]Still working... {elapsed_mins}m since last activity[/dim]")

            time_mod.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


def kill_peasant_process(pid: int, label: str = "") -> bool:
    """Kill a peasant process group (SIGTERM → wait → SIGKILL).

    Returns True if the process was killed, False if already dead or not found.
    """
    prefix = f"{label}: " if label else ""
    if pid <= 0:
        typer.echo(f"{prefix}invalid PID ({pid}), skipping kill")
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
        typer.echo(f"{prefix}sent SIGTERM to process group (pgid {pid})")
    except OSError:
        typer.echo(f"{prefix}process group {pid} not found (already dead)")
        return False

    # Wait for processes to exit, then SIGKILL stragglers
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except OSError:
            return True  # all dead
        time.sleep(0.2)

    # Still alive after timeout — force kill
    try:
        os.killpg(pid, signal.SIGKILL)
        typer.echo(f"{prefix}sent SIGKILL to process group (pgid {pid})")
    except OSError:
        pass
    return True


@peasant_app.command("stop", help="Stop a running peasant.")
def peasant_stop(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Force-close session state even without a PID.")] = False,
) -> None:
    """Send SIGTERM to the peasant process and update status to stopped."""
    from kingdom.session import get_agent_state, update_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    session_name = peasant_session_name(full_ticket_id)
    state = get_agent_state(base, feature, session_name)

    if state.status not in ("working", "awaiting_council", "needs_king_review"):
        print_error(f"Peasant {full_ticket_id} is not running (status: {state.status})")
        raise typer.Exit(code=1)

    if state.pid:
        kill_peasant_process(state.pid, full_ticket_id)
    elif not force:
        print_error(f"No PID found for peasant {full_ticket_id}. Use --force to close session state anyway.")
        raise typer.Exit(code=1)
    else:
        typer.echo(f"{full_ticket_id}: no PID found, force-closing session state")

    # Update session status
    now = datetime.now(UTC).isoformat()
    update_agent_state(
        base,
        feature,
        session_name,
        status="stopped",
        last_activity=now,
    )
    typer.echo("Status updated to stopped")


@peasant_app.command("clean", help="Remove a peasant's worktree.")
def peasant_clean(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt.")] = False,
) -> None:
    """Remove the git worktree for a ticket."""

    ctx = resolve_peasant_context(ticket_id)

    if not force:
        typer.confirm(f"Remove worktree for {ctx.full_ticket_id}?", abort=True)

    try:
        remove_worktree(ctx.base, ctx.full_ticket_id, git_root=ctx.git_root, feature=ctx.feature)
        typer.echo(f"{ctx.full_ticket_id}: worktree removed")
    except FileNotFoundError:
        print_error(f"No worktree found for {ctx.full_ticket_id}")
        raise typer.Exit(code=1) from None
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None


@peasant_app.command("prune", help="Clean up stale peasant sessions (dead processes, orphaned state).")
def peasant_prune(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Show what would be pruned without changing anything.")
    ] = False,
) -> None:
    """Find peasant sessions with dead/missing processes and mark them stopped."""
    from kingdom.session import list_active_agents, update_agent_state

    base = require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    active = list_active_agents(base, feature)
    peasants = [a for a in active if a.name.startswith("peasant-")]

    stale = []
    for p in peasants:
        if p.status in ("done", "failed", "stopped"):
            continue
        if not p.pid or not is_process_alive(p.pid):
            stale.append(p)

    if not stale:
        typer.echo("No stale peasant sessions found.")
        return

    for p in stale:
        reason = "no PID" if not p.pid else f"dead process (pid {p.pid})"
        if dry_run:
            typer.echo(f"Would prune: {p.name} (status: {p.status}, {reason})")
        else:
            now = datetime.now(UTC).isoformat()
            update_agent_state(base, feature, p.name, status="stopped", last_activity=now)
            typer.echo(f"Pruned: {p.name} (was {p.status}, {reason})")

    if dry_run:
        typer.echo(f"\n{len(stale)} session(s) would be pruned. Run without --dry-run to apply.")
    else:
        typer.echo(f"\n{len(stale)} session(s) pruned.")


@peasant_app.command("sync", help="Pull parent branch changes into a peasant's worktree.")
def peasant_sync(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Merge the parent branch into the worktree's ticket branch, then refresh dependencies."""
    from kingdom.session import get_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    # Refuse if peasant is actively running
    session_name = peasant_session_name(full_ticket_id)
    state = get_agent_state(base, feature, session_name)
    if state.status == "working" and state.pid and is_process_alive(state.pid):
        print_error(f"Peasant is running on {full_ticket_id} (pid {state.pid}). Stop it first with `kd peasant stop`.")
        raise typer.Exit(code=1)

    # Find worktree
    worktree_path = existing_worktree_path_for(base, full_ticket_id, feature=feature)
    if not worktree_path.exists():
        print_error(f"No worktree found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1)

    # Merge parent branch into worktree
    parent_branch = feature
    typer.echo(f"[1/2] Merging {parent_branch} into worktree for {full_ticket_id}...")
    merge_result = subprocess.run(
        ["git", "merge", parent_branch, "--no-edit"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )

    if merge_result.returncode != 0:
        print_error("Merge failed.")
        if merge_result.stdout.strip():
            error_console.print(merge_result.stdout.strip())
        if merge_result.stderr.strip():
            error_console.print(merge_result.stderr.strip())
        subprocess.run(["git", "merge", "--abort"], capture_output=True, cwd=worktree_path)
        error_console.print(f"\nMerge aborted. To resolve manually:\n  cd {worktree_path}\n  git merge {parent_branch}")
        raise typer.Exit(code=1)

    merge_out = merge_result.stdout.strip()
    if "Already up to date" in merge_out:
        typer.echo("Already up to date.")
    elif merge_out:
        typer.echo(merge_out)

    # Run init-worktree.sh to refresh dependencies
    run_init_script(base, worktree_path, step_prefix="[2/2] ", log=typer.echo)

    typer.echo(f"{full_ticket_id}: sync complete")


@peasant_app.command("msg", help="Send a directive to a working peasant.")
def peasant_msg(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    message: Annotated[str, typer.Argument(help="Directive message for the peasant.")],
) -> None:
    """Write a directive to the work thread; the peasant picks it up on next loop iteration."""
    from kingdom.thread import add_message

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    thread_id = peasant_thread_id(full_ticket_id)

    try:
        add_message(base, feature, thread_id, from_="king", to=peasant_session_name(full_ticket_id), body=message)
    except FileNotFoundError:
        print_error(f"No work thread found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1) from None

    typer.echo(f"{full_ticket_id}: directive sent")

    # Warn if peasant is not running
    from kingdom.session import get_agent_state

    session_name = peasant_session_name(full_ticket_id)
    state = get_agent_state(base, feature, session_name)
    process_alive = state.status == "working" and state.pid and is_process_alive(state.pid)
    if not process_alive:
        typer.echo(
            f"Warning: peasant is not running (status: {state.status}). Message won't be picked up until restarted."
        )


@peasant_app.command("read", help="Show messages from a peasant.")
def peasant_read(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    last: Annotated[int, typer.Option("--last", "-n", help="Number of messages to show.", min=1)] = 10,
) -> None:
    """Show recent messages from the peasant (escalations, status updates)."""
    from kingdom.thread import list_messages

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    thread_id = peasant_thread_id(full_ticket_id)
    session_name = peasant_session_name(full_ticket_id)

    try:
        messages = list_messages(base, feature, thread_id)
    except FileNotFoundError:
        print_error(f"No work thread found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1) from None

    # Filter to messages from the peasant
    peasant_msgs = [m for m in messages if m.from_ == session_name]

    if not peasant_msgs:
        typer.echo(f"No messages from {session_name} yet. The peasant may still be working.")
        return

    # Show last N messages
    console = Console()
    for msg in peasant_msgs[-last:]:
        ts = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        header = f"## [{ts}] {msg.from_} → {msg.to}"
        console.print(Markdown(f"{header}\n\n{msg.body}"))


@peasant_app.command("review", help="Review a peasant's completed work.")
def peasant_review(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Show diff, worklog, and council feedback for a peasant's work."""
    from kingdom.harness import extract_worklog
    from kingdom.session import get_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, ticket, ticket_path = ctx.base, ctx.ticket, ctx.ticket_path
    full_ticket_id, feature = ctx.full_ticket_id, ctx.feature

    session_name = peasant_session_name(full_ticket_id)
    thread_id = peasant_thread_id(full_ticket_id)
    branch_name = f"ticket/{full_ticket_id}"

    console = Console()

    # 1. Show diff
    review_state = get_agent_state(base, feature, session_name)
    if review_state.hand_mode:
        if review_state.start_sha:
            diff_spec = f"{review_state.start_sha}..HEAD"
        else:
            diff_spec = "HEAD"
    else:
        diff_spec = f"HEAD...{branch_name}"
    diff_result = subprocess.run(
        ["git", "diff", diff_spec, "--stat"],
        capture_output=True,
        text=True,
        cwd=str(ctx.git_root),
    )
    diff_output = diff_result.stdout.strip()
    diff_err = diff_result.stderr.strip()
    has_diff = False
    if diff_result.returncode != 0 and diff_err:
        console.print(Markdown(f"## diff error: {diff_spec}\n\n```\n{diff_err}\n```"))
    elif diff_output:
        has_diff = True
        console.print(Markdown(f"## diff: {diff_spec}\n\n```\n{diff_output}\n```"))
    else:
        styled_echo("⚠ No code diff — the peasant may not have made any changes.", fg=typer.colors.YELLOW)

    # 2. Show worklog
    worklog = extract_worklog(ticket_path)
    if worklog:
        console.print(Markdown(f"## Worklog\n\n{worklog}"))
    else:
        typer.echo("(no worklog entries)")

    # 3. Show council feedback (messages from council members in the work thread)
    try:
        from kingdom.thread import list_messages

        messages = list_messages(base, feature, thread_id)
        council_msgs = [m for m in messages if m.from_ not in ("king", session_name)]
        if council_msgs:
            feedback_parts = []
            for msg in council_msgs:
                feedback_parts.append(f"### {msg.from_}\n\n{msg.body}")
            console.print(Markdown("## Council Feedback\n\n" + "\n\n---\n\n".join(feedback_parts)))
    except FileNotFoundError:
        pass  # No work thread yet — skip council feedback

    # 4. Show session status
    state = get_agent_state(base, feature, session_name)
    typer.echo(f"\nTicket status: {ticket.status}")
    typer.echo(f"Peasant status: {state.status}")
    if state.review_bounce_count:
        typer.echo(f"Review bounces: {state.review_bounce_count}")

    # Warn if no code diff
    if not has_diff and state.status == "needs_king_review":
        styled_echo("\nWarning: no code diff detected — peasant may not have made meaningful changes.", fg="yellow")

    # Prompt for action
    can_accept = ticket.status == "in_review" and state.status in {"needs_king_review", "done"}
    if can_accept:
        typer.echo(f"\nUse `kd peasant accept {full_ticket_id}` or `kd peasant reject {full_ticket_id} 'feedback'`.")
    else:
        typer.echo(f"\nUse `kd peasant reject {full_ticket_id} 'feedback'` to send feedback.")


@peasant_app.command("approve", help="Accept a peasant's work and close the ticket.", hidden=True)
@peasant_app.command("accept", help="Accept a peasant's work and close the ticket.")
def peasant_accept(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Accept a peasant's completed work: merge changes and close the ticket."""
    ctx = resolve_peasant_context(ticket_id)
    lock_path = branch_root(ctx.base, ctx.feature) / ".peasant-accept.lock"
    try:
        with flock(lock_path, timeout_seconds=PEASANT_LOCK_TIMEOUT_SECONDS):
            accept_peasant(ctx)
    except TimeoutError:
        print_error("Another peasant acceptance is still running. Retry shortly.")
        raise typer.Exit(code=1) from None


def accept_peasant(ctx: PeasantContext) -> None:
    """Integrate one reviewed peasant while holding the branch accept lock."""
    from kingdom.session import get_agent_state, update_agent_state

    base = ctx.base
    full_ticket_id = ctx.full_ticket_id

    session_name = peasant_session_name(full_ticket_id)
    branch_name = f"ticket/{full_ticket_id}"

    owning_features: list[str] = []
    branch_directory = branches_root(base)
    if branch_directory.exists():
        for feature_directory in sorted(branch_directory.iterdir()):
            if not feature_directory.is_dir():
                continue
            session_file = feature_directory / "sessions" / f"{session_name}.json"
            if not session_file.exists():
                continue
            session_data = read_json(session_file)
            if session_data.get("status", "idle") != "idle":
                owning_features.append(feature_directory.name)

    if len(owning_features) != 1:
        if owning_features:
            features = ", ".join(owning_features)
            print_error(f"Cannot accept: {session_name} exists in multiple Kingdom features: {features}.")
        else:
            print_error(f"Cannot accept: no active Kingdom session records {full_ticket_id}.")
        error_console.print(f"Review the exact worker: `kd peasant review {full_ticket_id}`")
        error_console.print(f"Retry exact acceptance: `kd peasant accept {full_ticket_id}`")
        raise typer.Exit(code=1)

    feature = owning_features[0]
    ticket, ticket_path = resolve_ticket_or_exit(base, full_ticket_id, branch=feature)
    state = get_agent_state(base, feature, session_name)
    if state.ticket and state.ticket != full_ticket_id:
        print_error(f"Cannot accept: {session_name} records ticket '{state.ticket}', not '{full_ticket_id}'.")
        error_console.print(f"Review the exact worker: `kd peasant review {full_ticket_id}`")
        raise typer.Exit(code=1)

    # Gate: ticket must be in_review
    if ticket.status != "in_review":
        print_error(f"Cannot accept: ticket is '{ticket.status}', expected 'in_review'.")
        raise typer.Exit(code=1)

    # Gate: session must be needs_king_review or done
    # A peasant may close the ticket prematurely (session → done) before the
    # normal council-review flow sets needs_king_review.  Both are acceptable.
    acceptable_statuses = {"needs_king_review", "done"}
    if state.status not in acceptable_statuses:
        print_error(f"Cannot accept: session is '{state.status}', expected one of {sorted(acceptable_statuses)}.")
        raise typer.Exit(code=1)

    current_branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(ctx.git_root),
    )
    current_branch = current_branch_result.stdout.strip()
    if current_branch_result.returncode != 0 or not current_branch or current_branch == "HEAD":
        print_error("Cannot accept from a detached or unresolved Git HEAD.")
        error_console.print(f"Review the exact worker: `kd peasant review {full_ticket_id}`")
        raise typer.Exit(code=1)

    if state.hand_mode:
        # Hand mode: changes are already on the invocation checkout, skip merge.
        typer.echo(f"Hand mode — changes already on {current_branch}, skipping merge")
    else:
        workspace_state = read_json(branch_root(base, feature) / "state.json")
        recorded_branch = workspace_state.get("branch")
        if isinstance(recorded_branch, str) and recorded_branch.strip():
            integration_branch = recorded_branch.strip()
            correct_checkout = current_branch == integration_branch
        else:
            integration_branch = feature
            correct_checkout = normalize_branch_name(current_branch) == normalize_branch_name(feature)

        if not correct_checkout:
            print_error(
                f"Cannot accept: workspace '{feature}' integrates into Git branch "
                f"'{integration_branch}', but HEAD is on '{current_branch}'."
            )
            error_console.print(f"Switch to the integration branch: `git switch {shlex.quote(integration_branch)}`")
            error_console.print(f"Then retry: `kd peasant accept {full_ticket_id}`")
            raise typer.Exit(code=1)

        # Worktree mode: merge ticket branch into feature branch
        # Check if already merged (idempotent re-run after manual conflict resolution)
        already_merged = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch_name, "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(ctx.git_root),
        )
        if already_merged.returncode == 0:
            typer.echo(f"{branch_name} already merged into {current_branch}, skipping merge")
        else:
            # Check for uncommitted changes before attempting merge
            uncommitted = check_uncommitted_changes(ctx.git_root, ignore_kd=True)
            if uncommitted:
                print_error(
                    f"Uncommitted changes on {current_branch} — commit or stash before accepting.\n"
                    f"  Found {len(uncommitted)} changed file(s)."
                )
                raise typer.Exit(code=1)

            merge_result = subprocess.run(
                ["git", "merge", branch_name, "--no-edit"],
                capture_output=True,
                text=True,
                cwd=str(ctx.git_root),
            )
            if merge_result.returncode != 0:
                # Integration failed — keep in_review, show recovery steps
                merge_err = merge_result.stdout.strip()
                if merge_result.stderr.strip():
                    merge_err += "\n" + merge_result.stderr.strip()
                print_error("Integration failed — merge conflicts detected. Ticket remains in_review.")
                error_console.print(f"\n{merge_err}\n")
                error_console.print("Recovery steps:")
                error_console.print(f"  1. Resolve conflict markers in the working tree (you are on {current_branch})")
                error_console.print("  2. git add <resolved files> && git commit")
                error_console.print(f"  3. kd peasant accept {full_ticket_id}  (re-run — detects merge is done)")
                raise typer.Exit(code=1)

            typer.echo(f"Integrated {branch_name} into {current_branch}")

    ticket.status = "closed"
    write_ticket(ticket, ticket_path)
    update_agent_state(
        base,
        feature,
        session_name,
        status="done",
        last_activity=datetime.now(UTC).isoformat(),
    )
    if not state.hand_mode:
        cleanup_accepted_peasant(ctx, branch_name)
    typer.echo(f"{full_ticket_id}: accepted — ticket closed")


def cleanup_accepted_peasant(ctx: PeasantContext, branch_name: str) -> None:
    """Best-effort cleanup after accepting a peasant's work."""
    try:
        remove_worktree(ctx.base, ctx.full_ticket_id, git_root=ctx.git_root, feature=ctx.feature)
        typer.echo(f"Removed worktree for {ctx.full_ticket_id}")
    except FileNotFoundError:
        styled_echo(f"Warning: no worktree found for {ctx.full_ticket_id}; skipping worktree cleanup.", fg="yellow")
    except RuntimeError as exc:
        styled_echo(f"Warning: could not remove worktree for {ctx.full_ticket_id}: {exc}", fg="yellow")

    result = subprocess.run(
        ["git", "branch", "-D", branch_name],
        capture_output=True,
        text=True,
        cwd=str(ctx.git_root),
        timeout=10,
    )
    if result.returncode == 0:
        typer.echo(f"Deleted branch {branch_name}")
        return

    message = result.stderr.strip() or result.stdout.strip() or "unknown error"
    styled_echo(f"Warning: could not delete branch {branch_name}: {message}", fg="yellow")


@peasant_app.command("reject", help="Reject a peasant's work with feedback.")
def peasant_reject(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    feedback: Annotated[str, typer.Argument(help="Feedback message for the peasant.")],
    no_resume: Annotated[bool, typer.Option("--no-resume", help="Don't auto-resume peasant on reject.")] = False,
) -> None:
    """Reject a peasant's work: send feedback and optionally relaunch the peasant."""
    import kingdom.cli as _cli
    from kingdom.session import get_agent_state, update_agent_state
    from kingdom.thread import add_message

    ctx = resolve_peasant_context(ticket_id)
    base, ticket, ticket_path = ctx.base, ctx.ticket, ctx.ticket_path
    full_ticket_id, feature = ctx.full_ticket_id, ctx.feature

    session_name = peasant_session_name(full_ticket_id)
    thread_id = peasant_thread_id(full_ticket_id)

    # Gate: ticket must be in_review
    if ticket.status != "in_review":
        print_error(f"Cannot reject: ticket is '{ticket.status}', expected 'in_review'.")
        raise typer.Exit(code=1)

    # Gate: session must be needs_king_review
    state = get_agent_state(base, feature, session_name)
    if state.status != "needs_king_review":
        print_error(f"Cannot reject: session is '{state.status}', expected 'needs_king_review'.")
        raise typer.Exit(code=1)

    # Kill the process if it's still alive (regardless of --no-resume)
    if state.pid and is_process_alive(state.pid):
        if no_resume:
            kill_peasant_process(state.pid, full_ticket_id)
        else:
            print_error(f"Peasant process (pid {state.pid}) is still alive. Stop it first or use --no-resume.")
            raise typer.Exit(code=1)

    try:
        add_message(base, feature, thread_id, from_="king", to=session_name, body=feedback)
    except FileNotFoundError:
        print_error(f"No work thread found for {full_ticket_id}. Start one with `kd peasant start {full_ticket_id}`.")
        raise typer.Exit(code=1) from None

    # Transition ticket back to in_progress
    ticket.status = "in_progress"
    write_ticket(ticket, ticket_path)

    if no_resume:
        update_agent_state(
            base,
            feature,
            session_name,
            status="stopped",
            pid=None,
            review_bounce_count=0,
            last_activity=datetime.now(UTC).isoformat(),
        )
        typer.echo(f"{full_ticket_id}: rejected — feedback sent, peasant stopped")
        return

    # Auto-resume: relaunch the peasant
    agent_backend = state.agent_backend or "claude"

    if state.hand_mode:
        # Hand mode: relaunch in-place using base repo
        from kingdom.session import list_active_agents

        for active in list_active_agents(base, feature):
            if active.name == session_name:
                continue
            if (
                active.status == "working"
                and active.pid
                and active.name.startswith("peasant-")
                and is_process_alive(active.pid)
            ):
                print_error(
                    f"Peasant {active.name} (pid {active.pid}) is already working on this checkout. "
                    "Stop it first or use --no-resume."
                )
                raise typer.Exit(code=1)
        worktree_path = ctx.git_root
    else:
        # Worktree mode: use the ticket worktree
        worktree_path = existing_worktree_path_for(base, full_ticket_id, feature=feature)
        if not worktree_path.exists():
            print_error(f"worktree missing for {full_ticket_id}. Run `kd peasant start` to recreate.")
            raise typer.Exit(code=1)

    pid = _cli.launch_work_background(
        base, feature, full_ticket_id, agent_backend, worktree_path, thread_id, session_name
    )

    now = datetime.now(UTC).isoformat()
    update_agent_state(
        base,
        feature,
        session_name,
        status="working",
        pid=pid,
        review_bounce_count=0,
        last_activity=now,
    )
    typer.echo(f"{full_ticket_id}: rejected — feedback sent, peasant relaunched (pid {pid})")
