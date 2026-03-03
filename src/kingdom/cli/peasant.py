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
    logs_root,
    normalize_branch_name,
    resolve_current_run,
)
from kingdom.ticket import Ticket, move_ticket, write_ticket
from kingdom.worktree import (
    create_worktree,
    remove_worktree,
    run_init_script,
    worktree_path_for,
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


class PeasantContext(NamedTuple):
    """Resolved ticket and (optionally) feature branch for a peasant command."""

    base: Path
    ticket: Ticket
    ticket_path: Path
    full_ticket_id: str
    feature: str


def resolve_peasant_context(ticket_id: str, base: Path | None = None, auto_pull: bool = False) -> PeasantContext:
    """Resolve ticket and feature branch, or exit with an error message.

    Handles the repeated preamble shared by peasant_* commands:
    find_ticket + AmbiguousTicketMatch handling + resolve_current_run.

    Args:
        auto_pull: If True, move backlog tickets into the current branch.
            Only set for mutating commands (peasant start).
    """
    base = base or require_project_root()

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
    except (ValueError, IndexError, subprocess.TimeoutExpired):
        pid = 0  # Can't determine PID — still functional

    return pid


@peasant_app.command("start", help="Launch a peasant agent on a ticket.")
def peasant_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID to work on.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent to use (default: from config).")] = None,
    hand: Annotated[bool, typer.Option("--hand", help="Run in current directory (serial mode).")] = False,
    tmux: Annotated[bool, typer.Option("--tmux", help="Open agent in a new tmux window.")] = False,
    watch: Annotated[bool, typer.Option("--watch", "-w", help="Watch peasant progress after starting.")] = False,
) -> None:
    """Create worktree, session, thread, and launch agent harness in background."""
    import kingdom.cli as _cli
    from kingdom.config import load_config
    from kingdom.session import update_agent_state
    from kingdom.thread import create_thread

    ctx = resolve_peasant_context(ticket_id, auto_pull=True)
    base, ticket, full_ticket_id, feature = ctx.base, ctx.ticket, ctx.full_ticket_id, ctx.feature

    # Block starting work on tickets that are in_review or closed
    if ticket.status in ("in_review", "closed"):
        print_error(f"Cannot start work on {full_ticket_id}: ticket is {ticket.status}")
        raise typer.Exit(code=1)

    # Transition open → in_progress
    if ticket.status == "open":
        ticket.status = "in_progress"
        write_ticket(ticket, ctx.ticket_path)

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
        worktree_path = base
        typer.echo(f"Running in hand mode (serial) on {base}")
    else:
        try:
            worktree_path = create_worktree(base, full_ticket_id, log=typer.echo)
        except RuntimeError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from None

    # Auto-assign ticket to the peasant session
    ticket.assignee = session_name
    write_ticket(ticket, ctx.ticket_path)

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
    update_agent_state(
        base,
        feature,
        session_name,
        status="working",
        ticket=full_ticket_id,
        thread=thread_id,
        agent_backend=agent,
        started_at=now,
        last_activity=now,
        hand_mode=hand,
    )

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

    if watch:
        typer.echo()
        peasant_watch(ticket_id)


TERMINAL_STATUSES = {"done", "failed", "stopped"}
WATCH_TERMINAL_STATUSES = {"done", "failed", "stopped", "needs_king_review", "blocked"}


@peasant_app.command("status", help="Show active peasants.")
def peasant_status(
    show_all: Annotated[bool, typer.Option("--all", "-a", help="Include completed/stopped peasants.")] = False,
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

    now = datetime.now(UTC)
    for p in peasants:
        ticket = p.ticket or p.name.replace("peasant-", "")

        # Calculate elapsed
        elapsed = ""
        if p.started_at:
            try:
                started = parse_iso_datetime(p.started_at)
                delta = now - started
                minutes = int(delta.total_seconds() / 60)
                elapsed = f"{minutes}m"
            except (ValueError, TypeError):
                elapsed = "?"

        # Format last activity
        last = ""
        if p.last_activity:
            try:
                last_dt = parse_iso_datetime(p.last_activity)
                ago = int((now - last_dt).total_seconds() / 60)
                last = f"{ago}m ago"
            except (ValueError, TypeError):
                last = "?"

        # Check if process is still alive
        display_status = p.status
        if p.pid and p.status == "working" and not is_process_alive(p.pid):
            display_status = "dead"

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
        }.get(display_status, "")

        agent_display = p.agent_backend or "?"

        table.add_row(
            ticket,
            agent_display,
            f"[{status_style}]{display_status}[/{status_style}]" if status_style else display_status,
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


@peasant_app.command("logs", help="Show peasant logs.")
def peasant_logs(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Tail logs continuously.")] = False,
) -> None:
    """Show stdout/stderr logs for a peasant."""
    ctx = resolve_peasant_context(ticket_id)

    session_name = peasant_session_name(ctx.full_ticket_id)
    peasant_logs_dir = logs_root(ctx.base, ctx.feature) / session_name
    stdout_log = peasant_logs_dir / "stdout.log"
    stderr_log = peasant_logs_dir / "stderr.log"

    if not peasant_logs_dir.exists():
        print_error(f"No logs found for {ctx.full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1)

    if follow:
        # Tail both stdout and stderr
        with contextlib.suppress(KeyboardInterrupt):
            files = [str(f) for f in [stdout_log, stderr_log] if f.exists()]
            if files:
                subprocess.run(["tail", "-f", *files])
            else:
                typer.echo("Log files are empty. The peasant may still be starting up.")
        return

    # Show both stdout and stderr
    console = Console()

    if stdout_log.exists() and stdout_log.stat().st_size > 0:
        content = stdout_log.read_text(encoding="utf-8")
        console.print(Markdown(f"## stdout\n\n```\n{content}\n```"))

    if stderr_log.exists() and stderr_log.stat().st_size > 0:
        content = stderr_log.read_text(encoding="utf-8")
        console.print(Markdown(f"## stderr\n\n```\n{content}\n```"))

    if not (stdout_log.exists() or stderr_log.exists()):
        typer.echo("Log files are empty. The peasant may still be starting up.")


FLAG_VERBS: dict[str, str] = {
    "M": "Editing",
    "A": "Created",
    "D": "Deleted",
    "R": "Renamed",
    "??": "New file",
}


def filter_agent_log_lines(lines: list[str], max_lines: int = 3, max_chars: int = 200, backend: str = "") -> list[str]:
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
    from kingdom.worktree import worktree_path_for

    ctx = _cli.resolve_peasant_context(ticket_id)
    session_name = peasant_session_name(ctx.full_ticket_id)

    console = Console()
    console.print(f"[bold]Watching {session_name}[/bold]  (Ctrl+C to stop)\n")

    # Resolve worktree path for activity polling
    state = get_agent_state(ctx.base, ctx.feature, session_name)
    worktree = ctx.base if state.hand_mode else worktree_path_for(ctx.base, ctx.full_ticket_id)

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
    last_worktree_status: list[str] | None = None
    worktree_poll_interval = 30.0  # seconds between worktree polls
    log_poll_interval = 15.0  # seconds between agent log polls
    agent_log_offset: int = 0  # byte offset into agent-live.log
    stream_buffer: str = ""  # carry-over buffer for reassemble_stream_text

    # Resolve agent live log path
    agent_live_log = logs_root(ctx.base, ctx.feature) / session_name / "agent-live.log"

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
                    "blocked": f"kd peasant logs {ctx.full_ticket_id}",
                    "failed": f"kd peasant logs {ctx.full_ticket_id}",
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

            # Heartbeat: if no activity for 60s, show a "still working" line
            silence = now - last_activity_time
            if silence >= 60 and now - last_heartbeat_time >= 60:
                last_heartbeat_time = now
                elapsed_mins = int(silence / 60)
                console.print(f"  [dim]Still working... {elapsed_mins}m since last activity[/dim]")

            time_mod.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


@peasant_app.command("stop", help="Stop a running peasant.")
def peasant_stop(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Send SIGTERM to the peasant process and update status to stopped."""
    from kingdom.session import get_agent_state, update_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    session_name = peasant_session_name(full_ticket_id)
    state = get_agent_state(base, feature, session_name)

    if state.status != "working":
        print_error(f"Peasant {full_ticket_id} is not running (status: {state.status})")
        raise typer.Exit(code=1)

    if not state.pid:
        print_error(f"No PID found for peasant {full_ticket_id}")
        raise typer.Exit(code=1)

    # Kill the entire process group (harness + backend + children).
    # The harness is launched with start_new_session=True, so its PID
    # is the process group leader.
    pgid = state.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
        typer.echo(f"{full_ticket_id}: sent SIGTERM to process group (pgid {pgid})")
    except OSError as e:
        typer.echo(f"Process group {pgid} not found: {e}")

    # Wait for processes to exit, then SIGKILL stragglers
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # check if any process in group is alive
        except OSError:
            break  # all dead
        time.sleep(0.2)
    else:
        # Still alive after timeout — force kill
        try:
            os.killpg(pgid, signal.SIGKILL)
            typer.echo(f"{full_ticket_id}: sent SIGKILL to process group (pgid {pgid})")
        except OSError:
            pass  # already dead

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
        remove_worktree(ctx.base, ctx.full_ticket_id)
        typer.echo(f"{ctx.full_ticket_id}: worktree removed")
    except FileNotFoundError:
        print_error(f"No worktree found for {ctx.full_ticket_id}")
        raise typer.Exit(code=1) from None
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None


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
    worktree_path = worktree_path_for(base, full_ticket_id)
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
        cwd=str(base),
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
    can_accept = ticket.status == "in_review" and state.status == "needs_king_review"
    if can_accept:
        typer.echo(f"\nUse `kd peasant accept {full_ticket_id}` or `kd peasant reject {full_ticket_id} 'feedback'`.")
    else:
        typer.echo(f"\nUse `kd peasant reject {full_ticket_id} 'feedback'` to send feedback.")


@peasant_app.command("accept", help="Accept a peasant's work and close the ticket.")
def peasant_accept(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Accept a peasant's completed work: merge changes and close the ticket."""
    from kingdom.session import get_agent_state, update_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, ticket, ticket_path = ctx.base, ctx.ticket, ctx.ticket_path
    full_ticket_id, feature = ctx.full_ticket_id, ctx.feature

    session_name = peasant_session_name(full_ticket_id)
    branch_name = f"ticket/{full_ticket_id}"

    # Gate: ticket must be in_review
    if ticket.status != "in_review":
        print_error(f"Cannot accept: ticket is '{ticket.status}', expected 'in_review'.")
        raise typer.Exit(code=1)

    # Gate: session must be needs_king_review
    state = get_agent_state(base, feature, session_name)
    if state.status != "needs_king_review":
        print_error(f"Cannot accept: session is '{state.status}', expected 'needs_king_review'.")
        raise typer.Exit(code=1)

    # Gate: must be on the feature branch
    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=str(base),
    ).stdout.strip()
    if normalize_branch_name(current_branch) != normalize_branch_name(feature):
        print_error(
            f"Cannot accept: expected to be on '{feature}' but HEAD is on '{current_branch}'. "
            "Switch branches and retry."
        )
        raise typer.Exit(code=1)

    if state.hand_mode:
        # Hand mode: changes are already on the feature branch, skip merge
        typer.echo(f"Hand mode — changes already on {feature}, skipping merge")
    else:
        # Worktree mode: merge ticket branch into feature branch
        worktree_path = worktree_path_for(base, full_ticket_id)
        merge_result = subprocess.run(
            ["git", "merge", branch_name, "--no-edit"],
            capture_output=True,
            text=True,
            cwd=str(base),
        )
        if merge_result.returncode != 0:
            # Integration failed — keep in_review, show recovery steps
            merge_err = merge_result.stdout.strip()
            if merge_result.stderr.strip():
                merge_err += "\n" + merge_result.stderr.strip()
            print_error("Integration failed — ticket remains in_review.")
            error_console.print(f"\n{merge_err}\n")
            error_console.print("Recovery steps:")
            error_console.print(f"  1. cd {worktree_path}")
            error_console.print(f"  2. git merge {feature} (resolve conflicts)")
            error_console.print(f"  3. kd peasant accept {full_ticket_id} (retry)")
            raise typer.Exit(code=1)

        typer.echo(f"Integrated {branch_name} into {feature}")

    ticket.status = "closed"
    write_ticket(ticket, ticket_path)
    update_agent_state(
        base,
        feature,
        session_name,
        status="done",
        last_activity=datetime.now(UTC).isoformat(),
    )
    typer.echo(f"{full_ticket_id}: accepted — ticket closed")


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

    # Gate: old process must be dead before relaunching
    if not no_resume and state.pid and is_process_alive(state.pid):
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
            status="working",
            pid=None,
            review_bounce_count=0,
            last_activity=datetime.now(UTC).isoformat(),
        )
        typer.echo(f"{full_ticket_id}: rejected — feedback sent, ticket back to in_progress")
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
        worktree_path = base
    else:
        # Worktree mode: use the ticket worktree
        worktree_path = worktree_path_for(base, full_ticket_id)
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
