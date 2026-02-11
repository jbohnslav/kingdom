"""Autonomous agent harness for peasant execution.

The harness runs an autonomous loop:
  1. Build prompt (ticket + acceptance criteria + worklog + new directives)
  2. Call backend CLI (agent commits its own changes)
  3. Parse response
  4. Append to worklog in ticket
  5. Update session file (status, resume_id, last_activity)
  6. Write response as message to work thread
  7. Check stop conditions: done, blocked, stopped, failed

Usage::

    kd agent run --agent claude --ticket kin-042 --worktree /path/to/worktree
"""

from __future__ import annotations

import logging
import re
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from kingdom.agent import build_command, load_agent, parse_response
from kingdom.session import get_agent_state, update_agent_state
from kingdom.state import resolve_current_run
from kingdom.thread import add_message, list_messages
from kingdom.ticket import find_ticket, read_ticket, write_ticket

logger = logging.getLogger("kingdom.harness")

MAX_ITERATIONS = 50
AGENT_TIMEOUT = 300  # 5 minutes per backend call


def build_prompt(ticket_body: str, worklog: str, directives: list[str], iteration: int) -> str:
    """Build the prompt sent to the backend agent.

    Combines ticket content, existing worklog, and any new directives
    from the work thread into a single prompt.
    """
    parts = []

    parts.append("You are a peasant agent working on a ticket. Work autonomously to complete it.")
    parts.append("")
    parts.append("## Ticket")
    parts.append(ticket_body)

    if worklog:
        parts.append("")
        parts.append("## Current Worklog")
        parts.append(worklog)

    if directives:
        parts.append("")
        parts.append("## Directives from Lead")
        for d in directives:
            parts.append(f"- {d}")

    parts.append("")
    parts.append("## Instructions")
    parts.append(f"This is iteration {iteration} of your work loop.")
    parts.append("Work on the ticket. Commit your changes as you go with descriptive commit messages.")
    parts.append("When you respond, structure your output as:")
    parts.append("1. What you did this iteration")
    parts.append("2. Your status: DONE, BLOCKED, or CONTINUE")
    parts.append("3. If BLOCKED, explain what you need help with")
    parts.append("4. If DONE, confirm all acceptance criteria are met")
    parts.append("")
    parts.append("End your response with exactly one of these status lines:")
    parts.append("STATUS: DONE")
    parts.append("STATUS: BLOCKED")
    parts.append("STATUS: CONTINUE")

    return "\n".join(parts)


def parse_status(response_text: str) -> str:
    """Extract the agent's reported status from its response.

    Looks for STATUS: DONE|BLOCKED|CONTINUE at end of response.
    Returns 'continue' if no status line found.
    """
    for line in reversed(response_text.strip().splitlines()):
        line = line.strip()
        match = re.match(r"^STATUS:\s*(DONE|BLOCKED|CONTINUE)$", line, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return "continue"


def extract_worklog_entry(response_text: str) -> str:
    """Extract a concise worklog entry from the agent's response.

    Takes the first substantive paragraph before the STATUS line.
    """
    lines = []
    for line in response_text.strip().splitlines():
        if re.match(r"^STATUS:\s*(DONE|BLOCKED|CONTINUE)$", line.strip(), re.IGNORECASE):
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    # Take first paragraph or first 200 chars
    paragraphs = text.split("\n\n")
    entry = paragraphs[0].strip() if paragraphs else text
    if len(entry) > 300:
        entry = entry[:297] + "..."
    return entry


def append_worklog(ticket_path: Path, entry: str) -> None:
    """Append an entry to the ticket's worklog section.

    If no worklog section exists, creates one at the end of the ticket body.
    Worklog is always the last section, so we just append to the end.
    """
    ticket = read_ticket(ticket_path)
    timestamp = datetime.now(UTC).strftime("%H:%M")

    worklog_line = f"- [{timestamp}] {entry}"

    if "## Worklog" not in ticket.body:
        ticket.body = ticket.body.rstrip() + "\n\n## Worklog\n\n" + worklog_line
    else:
        ticket.body = ticket.body.rstrip() + "\n" + worklog_line

    write_ticket(ticket, ticket_path)


def extract_worklog(ticket_path: Path) -> str:
    """Extract the worklog section from a ticket.

    Worklog is always the last section, so everything after the header is worklog.
    """
    ticket = read_ticket(ticket_path)
    if "## Worklog" not in ticket.body:
        return ""

    _, after_header = ticket.body.split("## Worklog", 1)
    return after_header.strip()


def get_new_directives(base: Path, branch: str, thread_id: str, last_seen_seq: int) -> tuple[list[str], int]:
    """Get new directive messages from the work thread since last_seen_seq.

    Returns directives from the king/hand and the new high-water mark.
    """
    messages = list_messages(base, branch, thread_id)
    directives = []
    max_seq = last_seen_seq

    for msg in messages:
        if msg.sequence <= last_seen_seq:
            continue
        if msg.from_ == "king":
            directives.append(msg.body.strip())
        max_seq = max(max_seq, msg.sequence)

    return directives, max_seq


def run_tests(worktree: Path) -> tuple[bool, str]:
    """Run pytest in the worktree to verify work.

    Returns (passed, output): passed is True if tests pass.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=worktree,
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += "\n" + result.stderr.strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return True, "pytest not found, skipping verification"
    except subprocess.TimeoutExpired:
        return False, "Test suite timed out after 120s"


def run_lint(worktree: Path) -> tuple[bool, str]:
    """Run ruff check in the worktree to verify lint.

    Returns (passed, output): passed is True if lint passes.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "."],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=worktree,
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += "\n" + result.stderr.strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return True, "ruff not found, skipping lint check"
    except subprocess.TimeoutExpired:
        return False, "Lint check timed out after 60s"


def run_agent_loop(
    base: Path,
    branch: str,
    agent_name: str,
    ticket_id: str,
    worktree: Path,
    thread_id: str,
    session_name: str,
) -> str:
    """Run the autonomous agent loop.

    This is the main harness loop. It runs until the agent reports done,
    blocked, or an error occurs.

    Args:
        base: Project root.
        branch: Branch name.
        agent_name: Agent config name (e.g., "claude").
        ticket_id: Full ticket ID (e.g., "kin-042").
        worktree: Path to the git worktree.
        thread_id: Work thread ID.
        session_name: Session name for the peasant (e.g., "peasant-kin-042").

    Returns:
        Final status: "done", "blocked", "failed", or "stopped".
    """
    # Load agent config
    try:
        agent_config = load_agent(agent_name, base)
    except FileNotFoundError:
        from kingdom.agent import DEFAULT_AGENTS

        agent_config = DEFAULT_AGENTS.get(agent_name)
        if agent_config is None:
            logger.error("Unknown agent: %s", agent_name)
            return "failed"

    # Find ticket
    result = find_ticket(base, ticket_id)
    if result is None:
        logger.error("Ticket not found: %s", ticket_id)
        return "failed"
    ticket, ticket_path = result

    # Track whether we should stop
    stop_requested = False

    def handle_signal(signum: int, frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        logger.info("Stop signal received (signal %d)", signum)

    signal.signal(signal.SIGTERM, handle_signal)

    # Get agent session for resume_id
    agent_state = get_agent_state(base, branch, session_name)
    resume_id = agent_state.resume_id

    # Initialize last_seen_seq to the sequence of the last message sent by
    # this peasant, so that any king messages sent while we were down are
    # picked up as new directives on the first iteration.
    last_seen_seq = 0
    try:
        messages = list_messages(base, branch, thread_id)
        for msg in reversed(messages):
            if msg.from_ == session_name:
                last_seen_seq = msg.sequence
                break
    except FileNotFoundError:
        pass

    final_status = "failed"

    for iteration in range(1, MAX_ITERATIONS + 1):
        if stop_requested:
            final_status = "stopped"
            logger.info("Stopping at iteration %d (signal received)", iteration)
            break

        logger.info("=== Iteration %d ===", iteration)

        # Update session: working
        now = datetime.now(UTC).isoformat()
        update_agent_state(
            base,
            branch,
            session_name,
            status="working",
            last_activity=now,
        )

        # Re-read ticket (may have been updated by worklog appends)
        ticket = read_ticket(ticket_path)
        worklog = extract_worklog(ticket_path)

        # Check for new directives from the lead
        directives, last_seen_seq = get_new_directives(base, branch, thread_id, last_seen_seq)

        # Build prompt
        prompt = build_prompt(ticket.body, worklog, directives, iteration)

        # Call backend
        cmd = build_command(agent_config, prompt, resume_id)
        logger.info("Calling backend: %s", " ".join(cmd[:3]) + "...")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=AGENT_TIMEOUT,
                cwd=worktree,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            logger.error("Backend timed out after %ds", AGENT_TIMEOUT)
            append_worklog(ticket_path, "Backend call timed out")
            final_status = "failed"
            break
        except FileNotFoundError:
            cmd_name = agent_config.cli.split()[0]
            logger.error("Backend command not found: %s", cmd_name)
            append_worklog(ticket_path, f"Backend command not found: {cmd_name}")
            final_status = "failed"
            break

        # Check for stop signal after backend call returns
        if stop_requested:
            final_status = "stopped"
            logger.info("Stopping after backend call (signal received)")
            break

        # Log raw agent output so it appears in `kd peasant logs --follow`
        if proc.stdout.strip():
            logger.info("--- Agent stdout ---\n%s\n--- End agent stdout ---", proc.stdout.strip())
        if proc.stderr.strip():
            logger.info("--- Agent stderr ---\n%s\n--- End agent stderr ---", proc.stderr.strip())

        # Parse response
        text, new_session_id, _raw = parse_response(agent_config, proc.stdout, proc.stderr, proc.returncode)
        if new_session_id:
            resume_id = new_session_id
            update_agent_state(base, branch, session_name, resume_id=new_session_id)

        if not text and proc.returncode != 0:
            error_msg = proc.stderr.strip() or f"Exit code {proc.returncode}"
            logger.error("Backend error: %s", error_msg)
            append_worklog(ticket_path, f"Backend error: {error_msg}")
            final_status = "failed"
            break

        # Parse agent's status
        status = parse_status(text)
        logger.info("Agent status: %s", status)

        # Append to worklog
        worklog_entry = extract_worklog_entry(text)
        if worklog_entry:
            append_worklog(ticket_path, worklog_entry)

        # Write response to work thread
        try:
            add_message(
                base,
                branch,
                thread_id,
                from_=session_name,
                to="king",
                body=text,
            )
        except FileNotFoundError:
            logger.warning("Could not write to thread %s", thread_id)

        # Update session timestamp
        now = datetime.now(UTC).isoformat()
        update_agent_state(base, branch, session_name, last_activity=now)

        # Check stop conditions
        if status == "done":
            # Verify by running quality gates (pytest + ruff) before accepting done
            logger.info("Agent reports DONE — running quality gates...")
            tests_passed, test_output = run_tests(worktree)
            lint_passed, lint_output = run_lint(worktree)

            if tests_passed and lint_passed:
                final_status = "done"
                logger.info("Quality gates passed (pytest + ruff), accepting DONE")
                append_worklog(ticket_path, "Quality gates passed (pytest + ruff) — marking done")
            else:
                failures = []
                if not tests_passed:
                    failures.append(f"pytest:\n{test_output}")
                if not lint_passed:
                    failures.append(f"ruff:\n{lint_output}")
                failure_detail = "\n\n".join(failures)
                logger.warning("Quality gates failed, overriding DONE to CONTINUE:\n%s", failure_detail)
                summary = []
                if not tests_passed:
                    summary.append("pytest failed")
                if not lint_passed:
                    summary.append("ruff failed")
                append_worklog(ticket_path, f"DONE rejected ({', '.join(summary)}). See logs for details.")
                # Don't break — continue the loop so agent can fix
                continue
            break
        elif status == "blocked":
            final_status = "blocked"
            logger.info("Agent reports BLOCKED")
            break
        # else: continue

    else:
        # Max iterations reached
        logger.warning("Max iterations (%d) reached", MAX_ITERATIONS)
        append_worklog(ticket_path, f"Max iterations ({MAX_ITERATIONS}) reached without completion")
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

    logger.info("Harness finished with status: %s", final_status)
    return final_status


def main() -> None:
    """Entry point for `kd agent run`."""
    import argparse

    parser = argparse.ArgumentParser(description="Run autonomous agent loop")
    parser.add_argument("--agent", required=True, help="Agent name (e.g., claude)")
    parser.add_argument("--ticket", required=True, help="Ticket ID (e.g., kin-042)")
    parser.add_argument("--worktree", required=True, help="Path to git worktree")
    parser.add_argument("--thread", required=True, help="Work thread ID")
    parser.add_argument("--session", required=True, help="Session name (e.g., peasant-kin-042)")
    parser.add_argument("--base", default=".", help="Project root")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    base = Path(args.base).resolve()
    branch = resolve_current_run(base)
    worktree = Path(args.worktree).resolve()

    status = run_agent_loop(
        base=base,
        branch=branch,
        agent_name=args.agent,
        ticket_id=args.ticket,
        worktree=worktree,
        thread_id=args.thread,
        session_name=args.session,
    )

    sys.exit(0 if status == "done" else 1)


if __name__ == "__main__":
    main()
