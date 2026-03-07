"""Lord agent harness — epic-scoped supervisor that orchestrates peasants.

The lord is an LLM session (Opus-tier) scoped to one epic's child tickets.
It discovers startable tickets, launches peasants, monitors completions,
performs cross-ticket integration review, accepts/rejects with feedback,
resolves merge conflicts, logs decisions, and exits when the epic is done.

Called by ``python -m kingdom.lord_worker`` (spawned by ``kd lord start``).
"""

from __future__ import annotations

import logging
import re
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from kingdom.agent import build_command, clean_agent_env, parse_response, resolve_agent
from kingdom.session import get_agent_state, update_agent_state
from kingdom.state import logs_root
from kingdom.ticket import (
    Ticket,
    append_worklog_entry,
    filter_worklog_lines,
    find_ticket,
    list_tickets,
    read_ticket,
)

logger = logging.getLogger("kingdom.lord_harness")

MAX_REQUEUE_ATTEMPTS = 3
POLL_INTERVAL_SECONDS = 30
MAX_PARALLEL_PEASANTS = 10
MAX_WORKLOG_ENTRIES = 30

# Idle detection backoff parameters
BACKOFF_STEPS = (5, 15, 30, 60)  # escalating delays, cap at 60s
WAITING_DELAY = 30  # delay after agent returns WAITING


def lord_session_name(epic_id: str) -> str:
    """Return the canonical session name for a lord orchestrating *epic_id*."""
    return f"lord-{epic_id}"


def format_lord_timestamp(dt: datetime) -> str:
    """Format a worklog timestamp in local time for lord entries."""
    local_dt = dt.astimezone()
    today = datetime.now().astimezone().date()
    if local_dt.date() == today:
        return f"[{local_dt.strftime('%H:%M')}]"
    return f"[{local_dt.strftime('%Y-%m-%d %H:%M')}]"


def append_lord_worklog(ticket_path: Path, entry: str, epic_id: str = "") -> None:
    """Append an entry to the epic ticket's worklog, tagged as lord-<epic_id>."""
    now = datetime.now(UTC)
    author = lord_session_name(epic_id) if epic_id else None
    append_worklog_entry(ticket_path, entry, timestamp=now, timestamp_text=format_lord_timestamp(now), author=author)


def discover_epic_children(base: Path, branch: str, epic_id: str) -> list[Path]:
    """Find all ticket files that are children of the given epic."""
    from kingdom.state import branch_root

    tickets_dir = branch_root(base, branch) / "tickets"
    if not tickets_dir.exists():
        return []

    children = []
    for ticket_path in tickets_dir.glob("*.md"):
        try:
            ticket = read_ticket(ticket_path)
            if ticket.parent == epic_id:
                children.append(ticket_path)
        except (ValueError, FileNotFoundError):
            continue
    return children


def get_startable_children(
    base: Path,
    branch: str,
    epic_id: str,
    *,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> list[tuple[Path, str]]:
    """Find epic children that are open/ready and not assigned to a running peasant.

    Returns list of (ticket_path, ticket_id) for startable tickets.

    If *children* / *tickets* are provided they are reused instead of
    re-discovering from disk.
    """
    if children is None:
        children = discover_epic_children(base, branch, epic_id)
    if not children:
        return []

    # Build status map for dep checking
    from kingdom.state import branch_root

    tickets_dir = branch_root(base, branch) / "tickets"
    all_tickets = list_tickets(tickets_dir)
    status_by_id = {t.id: t.status for t in all_tickets}

    startable = []
    for ticket_path in children:
        ticket = tickets[ticket_path.stem] if tickets else read_ticket(ticket_path)

        # Skip closed, in_review, or already in_progress tickets
        if ticket.status != "open":
            continue

        # Skip epic-type children (shouldn't happen but be safe)
        if ticket.type == "epic":
            continue

        # Check deps are all closed
        has_open_dep = any(status_by_id.get(d, "unknown") != "closed" for d in ticket.deps)
        if has_open_dep:
            continue

        # Check no active peasant already working on it
        session_name = f"peasant-{ticket.id}"
        state = get_agent_state(base, branch, session_name)
        if state.status in ("working", "awaiting_council"):
            continue

        startable.append((ticket_path, ticket.id))

    return startable


def get_active_peasants(
    base: Path,
    branch: str,
    epic_id: str,
    *,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> list[tuple[str, str, str]]:
    """Get peasants currently working on epic children.

    Returns list of (ticket_id, session_name, status).

    If *children* / *tickets* are provided they are reused instead of
    re-discovering from disk.
    """
    if children is None:
        children = discover_epic_children(base, branch, epic_id)
    active = []
    for ticket_path in children:
        ticket = tickets[ticket_path.stem] if tickets else read_ticket(ticket_path)
        session_name = f"peasant-{ticket.id}"
        state = get_agent_state(base, branch, session_name)
        if state.status not in ("idle",):
            active.append((ticket.id, session_name, state.status))
    return active


def get_completed_peasants(
    base: Path,
    branch: str,
    epic_id: str,
    *,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> list[tuple[str, str]]:
    """Find peasants that have completed work and need lord attention.

    Matches session status ``needs_king_review`` (normal completion) as well as
    ``done`` with ticket ``in_review`` (diverged-state completion via peasant accept).

    Returns list of (ticket_id, session_name).

    If *children* / *tickets* are provided they are reused instead of
    re-discovering from disk.
    """
    if children is None:
        children = discover_epic_children(base, branch, epic_id)
    completed = []
    for ticket_path in children:
        ticket = tickets[ticket_path.stem] if tickets else read_ticket(ticket_path)
        session_name = f"peasant-{ticket.id}"
        state = get_agent_state(base, branch, session_name)
        if state.status == "needs_king_review" or (state.status == "done" and ticket.status == "in_review"):
            completed.append((ticket.id, session_name))
    return completed


def all_children_closed(
    base: Path,
    branch: str,
    epic_id: str,
    *,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> bool:
    """Check if all children of the epic are closed."""
    if children is None:
        children = discover_epic_children(base, branch, epic_id)
    if not children:
        return False
    for ticket_path in children:
        ticket = tickets[ticket_path.stem] if tickets else read_ticket(ticket_path)
        if ticket.status != "closed":
            return False
    return True


def has_actionable_work(
    base: Path,
    branch: str,
    epic_id: str,
    *,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> bool:
    """Check whether the current state has something the lord can act on.

    Returns True when at least one of these is true:
    - A startable child exists (open, deps met, no active peasant)
    - A peasant is ``needs_king_review``
    - No active peasants remain but open work still exists (stuck state)

    Note: ``all_children_closed`` and ``stop_requested`` are checked separately
    in the loop before this function is called.
    """
    if children is None:
        children = discover_epic_children(base, branch, epic_id)
    if tickets is None:
        tickets = {p.stem: read_ticket(p) for p in children}
    if get_startable_children(base, branch, epic_id, children=children, tickets=tickets):
        return True
    if get_completed_peasants(base, branch, epic_id, children=children, tickets=tickets):
        return True
    # No active peasants but open work exists → stuck, lord should investigate
    active = get_active_peasants(base, branch, epic_id, children=children, tickets=tickets)
    return bool(not active and any(t.status != "closed" for t in tickets.values()))


def get_children_summary(
    base: Path,
    branch: str,
    epic_id: str,
    *,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> tuple[tuple[str, str, str, tuple[tuple[str, str], ...]], ...]:
    """Snapshot the state of all epic children, their peasants, and dependency statuses.

    Returns a tuple of (ticket_id, ticket_status, peasant_status, dep_statuses)
    for each child, sorted by ticket_id for stable comparison.

    dep_statuses is a sorted tuple of (dep_id, dep_status) so the snapshot changes
    when an external dependency closes (making a child newly startable).
    """
    from kingdom.state import branch_root

    if children is None:
        children = discover_epic_children(base, branch, epic_id)

    # Build status map for deps (includes all tickets, not just epic children)
    tickets_dir = branch_root(base, branch) / "tickets"
    all_tickets = list_tickets(tickets_dir)
    status_by_id = {t.id: t.status for t in all_tickets}

    summary = []
    for child_path in children:
        ticket = tickets[child_path.stem] if tickets else read_ticket(child_path)
        session_name = f"peasant-{ticket.id}"
        state = get_agent_state(base, branch, session_name)
        dep_statuses = tuple(sorted((d, status_by_id.get(d, "unknown")) for d in ticket.deps))
        summary.append((ticket.id, ticket.status, state.status, dep_statuses))
    return tuple(sorted(summary))


def extract_bounded_worklog(body: str, *, max_entries: int = MAX_WORKLOG_ENTRIES) -> str:
    """Extract the worklog from an epic body, filtered and bounded for the lord prompt.

    Filters to lord-* and unknown (legacy) entries, then takes the most recent
    *max_entries* entries to prevent unbounded prompt growth.

    Returns the formatted worklog section text, or empty string if no entries.
    """
    if "## Worklog" not in body:
        return ""

    worklog_section = body.split("## Worklog", 1)[1]
    # Stop at the next heading (if any)
    next_heading = re.search(r"\n## ", worklog_section)
    if next_heading:
        worklog_section = worklog_section[: next_heading.start()]

    # Split into lines and filter
    lines = worklog_section.strip().splitlines()
    if not lines:
        return ""

    filtered = filter_worklog_lines(lines)
    if not filtered:
        return ""

    # Group into entries (each starting with "- ") and take the last N
    entries: list[list[str]] = []
    for line in filtered:
        if line.startswith("- "):
            entries.append([line])
        elif entries:
            entries[-1].append(line)

    if not entries:
        return ""

    bounded = entries[-max_entries:]
    entry_text = "\n".join(line for entry in bounded for line in entry)

    truncated = len(entries) > max_entries
    header = "## Recent Worklog"
    if truncated:
        header += f" (last {max_entries} of {len(entries)} entries)"

    return f"{header}\n\n{entry_text}"


def build_lord_prompt(
    epic_path: Path,
    epic_id: str,
    base: Path,
    branch: str,
    *,
    cycle_number: int = 1,
    stop_requested: bool = False,
    children: list[Path] | None = None,
    tickets: dict[str, Ticket] | None = None,
) -> str:
    """Build the system prompt for the lord agent session.

    The lord gets context about the epic, its children, their statuses,
    and a toolkit of kd commands to orchestrate work.

    If *children* / *tickets* are provided they are reused instead of
    re-discovering from disk.
    """
    epic = read_ticket(epic_path)
    if children is None:
        children = discover_epic_children(base, branch, epic_id)

    # Parse all child tickets once and reuse across helpers
    child_tickets: dict[str, Ticket] = tickets if tickets is not None else {p.stem: read_ticket(p) for p in children}

    # Build children status summary
    child_summary_lines = []
    requeue_tracker: dict[str, int] = {}
    for child_path in children:
        child = child_tickets[child_path.stem]
        session_name = f"peasant-{child.id}"
        state = get_agent_state(base, branch, session_name)
        deps_str = f" (deps: {', '.join(child.deps)})" if child.deps else ""
        status_detail = child.status
        if state.status not in ("idle",):
            status_detail = f"{child.status} / peasant: {state.status}"
            if state.review_bounce_count > 0:
                status_detail += f" (bounces: {state.review_bounce_count})"
                requeue_tracker[child.id] = state.review_bounce_count
        child_summary_lines.append(f"  - [{child.id}] {child.title} — {status_detail}{deps_str}")

    startable = get_startable_children(base, branch, epic_id, children=children, tickets=child_tickets)
    completed = get_completed_peasants(base, branch, epic_id, children=children, tickets=child_tickets)
    active = get_active_peasants(base, branch, epic_id, children=children, tickets=child_tickets)

    working_count = sum(1 for _, _, s in active if s in ("working", "awaiting_council"))
    completed_count = sum(1 for t in child_tickets.values() if t.status == "closed")

    parts = []

    # Identity
    parts.append(
        "You are a lord — an epic-scoped supervisor agent in Kingdom (kd). "
        "Your job is to orchestrate peasant workers on the children of an epic ticket. "
        "You do NOT write code yourself. Instead, you start peasants, monitor their progress, "
        "review their completed work at the cross-ticket integration level, accept or reject "
        "with feedback, resolve merge conflicts, and log all decisions to the epic worklog."
    )

    # Epic context
    parts.append("")
    parts.append(f"## Epic: {epic.title}")
    parts.append(f"**Epic ID:** {epic_id}")
    parts.append(f"**Epic ticket:** {epic_path}")
    parts.append("")
    # Show epic body (before worklog) plus bounded worklog context
    body_before_worklog = epic.body.split("## Worklog")[0].strip() if "## Worklog" in epic.body else epic.body.strip()
    if body_before_worklog:
        parts.append(body_before_worklog)
        parts.append("")
    worklog_context = extract_bounded_worklog(epic.body)
    if worklog_context:
        parts.append(worklog_context)
        parts.append("")

    # Children status
    parts.append("## Children Status")
    parts.append(f"Total: {len(children)} | Closed: {completed_count} | Working: {working_count}")
    if child_summary_lines:
        parts.append("")
        parts.extend(child_summary_lines)
    parts.append("")

    # Startable tickets
    if startable:
        parts.append(f"## Startable Tickets ({len(startable)})")
        for _, tid in startable:
            parts.append(f"  - {tid}")
        parts.append("")

    # Completed peasants awaiting review
    if completed:
        parts.append(f"## Completed Peasants Awaiting Review ({len(completed)})")
        for tid, _ in completed:
            parts.append(f"  - {tid}")
        parts.append("")

    # Requeue warnings
    high_bounce = {tid: count for tid, count in requeue_tracker.items() if count >= 2}
    if high_bounce:
        parts.append("## Escalation Warning")
        for tid, count in high_bounce.items():
            parts.append(f"  - {tid}: {count} bounces — escalate if next attempt fails")
        parts.append("")

    # Stop signal
    if stop_requested:
        parts.append("## STOP SIGNAL RECEIVED")
        parts.append(
            "A stop has been requested. Do NOT start new peasants. Wrap up any in-progress reviews and exit gracefully."
        )
        parts.append("")

    # Toolkit
    parts.append("## Your Toolkit")
    parts.append("Use these kd commands to orchestrate work:")
    parts.append("")
    parts.append("### Starting peasants")
    parts.append("`kd peasant start <ticket-id>` — Launch a peasant on a startable ticket")
    parts.append("")
    parts.append("### Monitoring")
    parts.append("`kd peasant status --json` — Check all active peasant statuses")
    parts.append("`kd peasant show <ticket-id> --json` — Show detailed peasant history")
    parts.append(f"`kd tk list --parent {epic_id}` — List all epic children")
    parts.append("`kd tk show <ticket-id>` — Show ticket details")
    parts.append("")
    parts.append("### Reviewing completed work")
    parts.append("`kd peasant review <ticket-id>` — Show diff, worklog, council feedback")
    parts.append("`kd peasant accept <ticket-id>` — Accept and merge peasant's work")
    parts.append("`kd peasant reject <ticket-id> 'feedback'` — Reject with guidance, auto-relaunches")
    parts.append("")
    parts.append("### Logging")
    parts.append(f'`kd tk log {epic_id} "message"` — Log decisions to epic worklog')
    parts.append("")
    parts.append("### Merge conflicts")
    parts.append("If `kd peasant accept` fails due to merge conflicts:")
    parts.append("1. Read the conflict markers in the affected files")
    parts.append("2. Edit to resolve the conflicts")
    parts.append("3. `git add <files>` and `git commit`")
    parts.append("4. `kd peasant accept <ticket-id>` again")
    parts.append("")

    # Instructions
    parts.append("## Instructions")
    parts.append(f"This is orchestration cycle {cycle_number}.")
    parts.append("")
    parts.append("Your workflow each cycle:")
    parts.append("1. **Discover** — Check for startable tickets and start peasants (up to ~10 parallel)")
    parts.append("2. **Monitor** — Check peasant statuses with `kd peasant status --json`")
    parts.append("3. **Review** — For completed peasants (needs_king_review), review their work:")
    parts.append("   - Check the diff and worklog with `kd peasant review <id>`")
    parts.append("   - Verify tickets compose cleanly at the cross-ticket level")
    parts.append("   - Accept good work, reject with specific guidance if issues found")
    parts.append("4. **Escalate** — If a ticket has been rejected 2-3 times, escalate to the King")
    parts.append("5. **Resolve** — Handle merge conflicts during accept")
    parts.append("6. **Log** — Log significant decisions to the epic worklog")
    parts.append("")
    parts.append("Key behaviors:")
    parts.append(f"- Start peasants on all startable tickets (max {MAX_PARALLEL_PEASANTS} parallel)")
    parts.append("- Don't re-review peasant work in detail — trust the council review")
    parts.append("- Focus on cross-ticket integration: do the changes compose cleanly?")
    parts.append("- Accept work that passes integration review")
    parts.append(f"- Reject with specific, actionable feedback (max {MAX_REQUEUE_ATTEMPTS} attempts per ticket)")
    parts.append(f"- After {MAX_REQUEUE_ATTEMPTS} failed attempts, report ESCALATE with the ticket ID and reason")
    parts.append("- Resolve merge conflicts directly rather than rejecting for them")
    parts.append("")
    parts.append("## Worklog Hygiene")
    parts.append("The epic worklog is **durable decision history**, not a live transcript.")
    parts.append("Only log to the epic worklog (`kd tk log`) on these events:")
    parts.append("- Peasant launched (which ticket, why now)")
    parts.append("- Peasant work accepted or rejected (with rationale)")
    parts.append("- Council bounce received")
    parts.append("- Escalation to the King")
    parts.append("- Merge conflict resolved")
    parts.append("- Blocked state entered or cleared")
    parts.append("- Epic completed")
    parts.append("")
    parts.append("Do NOT log idle observations, status checks, or 'nothing to do' entries.")
    parts.append("Per-cycle narration goes to stdout (captured in agent-live.log), not the worklog.")
    parts.append("")

    # Response format
    parts.append("## Response Format")
    parts.append("Start with a prose summary of actions taken this cycle.")
    parts.append("End with exactly one status line:")
    parts.append("")
    parts.append("STATUS: DONE — All epic children are closed, epic is complete")
    parts.append("STATUS: CONTINUE — More work to do, need another cycle")
    parts.append("STATUS: WAITING — Nothing actionable right now, all peasants working/in council review")
    parts.append("STATUS: BLOCKED — Cannot proceed, need King intervention")
    parts.append("STATUS: ESCALATE <ticket-id> — Ticket needs King attention after repeated failures")
    parts.append("STATUS: STOPPED — Stop signal received, shutting down gracefully")

    return "\n".join(parts)


def parse_lord_status(response_text: str) -> tuple[str, str | None]:
    """Extract the lord's reported status from its response.

    Returns (status, escalate_ticket_id).
    Status is one of: done, continue, blocked, escalate, stopped.
    """
    for line in reversed(response_text.strip().splitlines()):
        line = line.strip()
        match = re.match(r"^STATUS:\s*(DONE|CONTINUE|BLOCKED|STOPPED|WAITING)$", line, re.IGNORECASE)
        if match:
            return match.group(1).lower(), None
        match = re.match(r"^STATUS:\s*ESCALATE\s+(\S+)", line, re.IGNORECASE)
        if match:
            return "escalate", match.group(1)
    return "continue", None


def run_lord_loop(
    base: Path,
    branch: str,
    agent_name: str,
    epic_id: str,
    session_name: str,
    max_cycles: int = 200,
) -> str:
    """Run the lord orchestration loop.

    Each cycle: build prompt with epic state, call LLM, parse response,
    check if done/blocked/escalate, repeat.

    Returns final status: done, blocked, failed, stopped, escalate.
    """
    from kingdom.config import load_config

    cfg = load_config(base)
    agent_def = cfg.agents.get(agent_name)
    if agent_def is None:
        logger.error("Unknown agent: %s", agent_name)
        return "failed"
    agent_config = resolve_agent(agent_name, agent_def)

    # Find epic ticket
    result = find_ticket(base, epic_id)
    if result is None:
        logger.error("Epic ticket not found: %s", epic_id)
        return "failed"
    _, epic_path = result

    # Verify it's actually an epic
    epic = read_ticket(epic_path)
    if epic.type != "epic":
        logger.error("Ticket %s is not an epic (type: %s)", epic_id, epic.type)
        return "failed"

    # Signal handling
    stop_requested = False

    def handle_signal(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        logger.info("Stop signal received (signal %d)", signum)

    signal.signal(signal.SIGTERM, handle_signal)

    # Session state
    agent_state = get_agent_state(base, branch, session_name)
    resume_id = agent_state.resume_id

    final_status = "failed"
    last_seen_states: tuple[tuple[str, str, str, tuple[tuple[str, str], ...]], ...] | None = None
    consecutive_idle = 0

    for cycle in range(1, max_cycles + 1):
        # Check for stop: either SIGTERM signal or persisted "stopping" session state
        if not stop_requested:
            session_state = get_agent_state(base, branch, session_name)
            if session_state.status == "stopping":
                stop_requested = True
                logger.info("Stop detected via session state (stopping)")

        if stop_requested:
            final_status = "stopped"
            append_lord_worklog(epic_path, epic_id=epic_id, entry="Stop requested — shutting down gracefully")
            logger.info("Stopping at cycle %d", cycle)
            break

        # Discover children and parse tickets once per cycle iteration
        cycle_children = discover_epic_children(base, branch, epic_id)
        cycle_tickets: dict[str, Ticket] = {p.stem: read_ticket(p) for p in cycle_children}

        # Check if all children are closed
        if all_children_closed(base, branch, epic_id, children=cycle_children, tickets=cycle_tickets):
            final_status = "done"
            append_lord_worklog(epic_path, epic_id=epic_id, entry="All epic children closed — epic complete")
            logger.info("All children closed at cycle %d", cycle)
            break

        # --- Idle detection: snapshot state and check actionability ---
        current_states = get_children_summary(base, branch, epic_id, children=cycle_children, tickets=cycle_tickets)
        if current_states != last_seen_states:
            # State changed — update snapshot and reset backoff counter
            if consecutive_idle > 0:
                logger.info("State changed after %d idle skips", consecutive_idle)
            last_seen_states = current_states
            consecutive_idle = 0

            # Even though state changed, only wake the lord if something is actionable.
            # Non-actionable changes (e.g. working→awaiting_council) should still idle.
            if not has_actionable_work(base, branch, epic_id, children=cycle_children, tickets=cycle_tickets):
                logger.info("State changed but nothing actionable — idle skip (cycle %d)", cycle)
                print(
                    f"[lord-{epic_id}] state changed but nothing actionable — sleeping {BACKOFF_STEPS[0]}s",
                    flush=True,
                )
                time.sleep(BACKOFF_STEPS[0])
                continue
        else:
            # Nothing changed — apply escalating backoff and skip LLM call
            consecutive_idle += 1
            idx = min(consecutive_idle - 1, len(BACKOFF_STEPS) - 1)
            backoff_delay = BACKOFF_STEPS[idx]
            logger.info(
                "Idle skip %d — no state change, sleeping %ds (cycle %d)",
                consecutive_idle,
                backoff_delay,
                cycle,
            )
            print(
                f"[lord-{epic_id}] idle skip {consecutive_idle} — no state change, sleeping {backoff_delay}s",
                flush=True,
            )
            time.sleep(backoff_delay)
            continue

        # Update session: working
        now = datetime.now(UTC).isoformat()
        update_agent_state(
            base,
            branch,
            session_name,
            status="working",
            last_activity=now,
        )

        logger.info("Cycle %d/%d — calling lord agent", cycle, max_cycles)

        # Build prompt with current state (reuse cycle's children/tickets)
        prompt = build_lord_prompt(
            epic_path,
            epic_id,
            base,
            branch,
            cycle_number=cycle,
            stop_requested=stop_requested,
            children=cycle_children,
            tickets=cycle_tickets,
        )

        # Call agent
        cmd = build_command(agent_config, prompt, resume_id, streaming=True)
        logger.info("Calling backend for lord cycle %d", cycle)

        live_log_path = logs_root(base, branch) / session_name / "agent-live.log"

        try:
            proc = run_lord_streaming_subprocess(
                cmd,
                cwd=base,
                env=clean_agent_env(role="lord", agent_name=session_name, kd_base=str(base)),
                live_log_path=live_log_path,
            )
        except FileNotFoundError:
            cmd_name = agent_config.cli.split()[0]
            logger.error("Backend command not found: %s", cmd_name)
            append_lord_worklog(epic_path, epic_id=epic_id, entry=f"Backend command not found: {cmd_name}")
            final_status = "failed"
            break

        # Check for stop after agent call
        if stop_requested:
            final_status = "stopped"
            append_lord_worklog(
                epic_path, epic_id=epic_id, entry="STOP signal received after agent call — shutting down"
            )
            break

        # Parse response
        text, new_session_id, _raw = parse_response(agent_config, proc.stdout, proc.stderr, proc.returncode)
        if new_session_id:
            resume_id = new_session_id
            update_agent_state(base, branch, session_name, resume_id=new_session_id)

        if not text and proc.returncode != 0:
            error_msg = proc.stderr.strip() or f"Exit code {proc.returncode}"
            logger.error("Backend error: %s", error_msg)
            append_lord_worklog(epic_path, epic_id=epic_id, entry=f"Backend error: {error_msg}")
            final_status = "failed"
            break

        # Parse lord's status
        status, escalate_ticket = parse_lord_status(text)
        logger.info("Lord status: %s (escalate: %s)", status, escalate_ticket)

        # Log lord's summary to debug log (not the epic worklog — the lord
        # logs durable events itself via `kd tk log`)
        summary = extract_lord_summary(text)
        if summary:
            logger.info("Lord summary: %s", summary)

        # Update session timestamp
        now = datetime.now(UTC).isoformat()
        update_agent_state(base, branch, session_name, last_activity=now)

        if status == "done":
            final_status = "done"
            append_lord_worklog(epic_path, epic_id=epic_id, entry="Lord reports epic complete")
            break
        elif status == "blocked":
            final_status = "blocked"
            append_lord_worklog(epic_path, epic_id=epic_id, entry="Lord reports BLOCKED — needs King intervention")
            break
        elif status == "escalate":
            final_status = "blocked"
            msg = f"Lord ESCALATES ticket {escalate_ticket} — needs King attention"
            append_lord_worklog(epic_path, epic_id=epic_id, entry=msg)
            logger.warning("Escalation: %s", msg)
            # Don't break — lord can continue working other tickets
            # But if there's nothing else to do, it'll report DONE or BLOCKED next cycle
        elif status == "stopped":
            final_status = "stopped"
            append_lord_worklog(epic_path, epic_id=epic_id, entry="Lord stopping gracefully")
            break
        elif status == "waiting":
            # Agent says nothing actionable — use longer delay before next cycle
            logger.info("Lord reports WAITING — applying %ds delay", WAITING_DELAY)
            print(
                f"[lord-{epic_id}] agent waiting — " f"nothing actionable, sleeping {WAITING_DELAY}s",
                flush=True,
            )
            time.sleep(WAITING_DELAY)
            continue
        # else: continue to next cycle

        # Brief pause between cycles to avoid hammering
        if status == "continue":
            time.sleep(5)

    else:
        # Max cycles reached
        logger.warning("Max cycles (%d) reached", max_cycles)
        append_lord_worklog(epic_path, epic_id=epic_id, entry=f"Max cycles ({max_cycles}) reached without completion")
        final_status = "failed"

    # Final session update
    now = datetime.now(UTC).isoformat()
    update_agent_state(
        base,
        branch,
        session_name,
        status=final_status,
        last_activity=now,
    )

    logger.info("Lord harness finished with status: %s", final_status)
    return final_status


def extract_lord_summary(response_text: str) -> str:
    """Extract a summary from the lord's response for the worklog."""
    lines = []
    for line in response_text.strip().splitlines():
        if re.match(r"^STATUS:\s*(DONE|BLOCKED|CONTINUE|STOPPED|ESCALATE|WAITING)", line.strip(), re.IGNORECASE):
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    # Take first substantive paragraph
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        if re.match(r"^#{1,6}\s+\S", stripped) and "\n" not in stripped:
            continue
        if len(stripped) > 500:
            stripped = stripped[:497] + "..."
        return stripped
    return ""


def run_lord_streaming_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    live_log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with real-time streaming for the lord agent."""
    if live_log_path:
        live_log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=cwd,
        env=env,
        text=True,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def drain(stream, buf: list[str]) -> None:
        for line in stream:
            buf.append(line)
            if live_log_path:
                try:
                    with live_log_path.open("a", encoding="utf-8") as f:
                        f.write(line)
                except OSError:
                    pass

    stdout_thread = threading.Thread(target=drain, args=(proc.stdout, stdout_lines), daemon=True)
    stderr_thread = threading.Thread(target=drain, args=(proc.stderr, stderr_lines), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    proc.wait()

    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
