"""Autonomous agent harness for peasant execution.

The harness runs an autonomous loop:
  1. Build prompt (ticket + acceptance criteria + worklog + new directives)
  2. Call backend CLI (agent commits its own changes)
  3. Parse response
  4. Append to worklog in ticket
  5. Update session file (status, resume_id, last_activity)
  6. Write response as message to work thread
  7. Check stop conditions: done, blocked, stopped, failed

Called in-process by ``kd work <ticket>``.
"""

from __future__ import annotations

import logging
import re
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from kingdom.agent import build_command, clean_agent_env, parse_response, resolve_agent
from kingdom.session import get_agent_state, update_agent_state
from kingdom.thread import add_message, list_messages
from kingdom.ticket import append_worklog_entry, find_ticket, read_ticket, write_ticket

logger = logging.getLogger("kingdom.harness")


def build_prompt(
    ticket_path: Path,
    worklog: str,
    directives: list[str],
    iteration: int,
    max_iterations: int,
    phase_prompt: str = "",
) -> str:
    """Build the prompt sent to the backend agent.

    References the ticket file by path (so the agent can read it directly)
    and includes existing worklog and any new directives from the work thread.
    """
    parts = []

    if phase_prompt:
        parts.append(phase_prompt)
        parts.append("")

    parts.append("You are a peasant agent working on a ticket. Work autonomously to complete it.")
    parts.append("")
    parts.append("## Ticket")
    parts.append(f"Read the ticket file at: {ticket_path}")

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
    parts.append(f"This is iteration {iteration} of {max_iterations}.")
    parts.append("Work on the ticket. Commit your changes as you go with descriptive commit messages.")
    parts.append(
        "Before reporting DONE, run the project's tests, linter, and pre-commit hooks to make sure everything passes."
    )
    parts.append("When you respond, structure your output as:")
    parts.append("1. What you did this iteration")
    parts.append("2. Your status: DONE, BLOCKED, or CONTINUE")
    parts.append("3. If BLOCKED, explain what you need help with")
    parts.append("4. If DONE, confirm all acceptance criteria are met and tests/lint pass")
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


def format_worklog_timestamp(dt: datetime) -> str:
    """Format a worklog timestamp, including date when the entry is not from today.

    Returns "[HH:MM]" for today's entries, "[YYYY-MM-DD HH:MM]" for older ones.
    """
    today = datetime.now(UTC).date()
    if dt.date() == today:
        return f"[{dt.strftime('%H:%M')}]"
    return f"[{dt.strftime('%Y-%m-%d %H:%M')}]"


def append_worklog(ticket_path: Path, entry: str) -> None:
    now = datetime.now(UTC)
    append_worklog_entry(ticket_path, entry, timestamp=now, timestamp_text=format_worklog_timestamp(now))


def extract_worklog(ticket_path: Path) -> str:
    """Extract the worklog section from a ticket, stopping at the next heading."""
    ticket = read_ticket(ticket_path)
    if "## Worklog" not in ticket.body:
        return ""

    _, after_header = ticket.body.split("## Worklog", 1)
    # Stop at the next ## heading if one exists
    lines = after_header.split("\n")
    result = []
    for line in lines:
        if line.startswith("## "):
            break
        result.append(line)
    return "\n".join(result).strip()


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


def has_code_changes(worktree: Path, start_sha: str | None) -> bool:
    """Check whether the worktree has any changes (committed or uncommitted) since start_sha."""
    try:
        # Uncommitted changes (staged + unstaged)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
        # Committed changes since start_sha
        if start_sha:
            result = subprocess.run(
                ["git", "log", "--oneline", f"{start_sha}..HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        else:
            # No baseline — can't determine whether committed changes exist.
            # Assume they do to avoid rejecting valid work.
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Can't determine — assume there might be changes
        return True
    return False


def get_diff(worktree: Path, start_sha: str | None, feature_branch: str | None = None) -> str:
    """Get the diff of changes for council review.

    For worktree mode (feature_branch set): uses feature_branch...HEAD (three-dot
    merge-base diff) so only the peasant's own changes appear, not other peasants'
    work that was merged into the feature branch.

    For hand mode (feature_branch=None): uses start_sha..HEAD (two-dot).
    Falls back to showing all uncommitted + recent committed changes.
    """
    try:
        if feature_branch:
            # Worktree mode: three-dot merge-base diff against feature branch
            result = subprocess.run(
                ["git", "diff", f"{feature_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=30,
            )
            # Fall back to two-dot if three-dot fails (e.g. detached HEAD, missing ref)
            if result.returncode != 0 and start_sha:
                result = subprocess.run(
                    ["git", "diff", f"{start_sha}..HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=worktree,
                    timeout=30,
                )
        elif start_sha:
            result = subprocess.run(
                ["git", "diff", f"{start_sha}..HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=30,
            )
        else:
            # No start_sha — show diff of staged + unstaged changes
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=30,
            )
        if result.returncode == 0 and result.stdout.strip():
            diff = result.stdout.strip()
            # Truncate very large diffs to avoid overwhelming the council
            if len(diff) > 50000:
                diff = diff[:50000] + "\n\n... (diff truncated at 50k chars)"
            return diff
        return "(no changes detected)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(could not generate diff)"


def build_review_prompt(ticket_title: str, ticket_body: str, diff: str, worklog: str) -> str:
    """Build the prompt sent to council members for review."""
    parts = [
        "## Code Review Request",
        "",
        f"**Ticket:** {ticket_title}",
        "",
        "### Ticket Description",
        ticket_body.split("## Worklog")[0].strip() if "## Worklog" in ticket_body else ticket_body.strip(),
        "",
        "### Changes (diff)",
        "```diff",
        diff,
        "```",
    ]

    if worklog:
        parts.extend(
            [
                "",
                "### Worklog",
                worklog,
            ]
        )

    parts.extend(
        [
            "",
            "### Instructions",
            "Review this code change. Consider:",
            "- Correctness: does it do what the ticket asks?",
            "- Edge cases: are there unhandled scenarios?",
            "- Code quality: is it readable, maintainable, and well-structured?",
            "- Tests: are the changes adequately tested? Run the project's test suite and linter to verify.",
            "",
            "End your review with exactly one of these verdict lines:",
            "VERDICT: APPROVED",
            "VERDICT: BLOCKING",
            "",
            "Use BLOCKING only for issues that must be fixed before merge.",
            "Use APPROVED if the changes are acceptable (minor suggestions are fine with APPROVED).",
        ]
    )

    return "\n".join(parts)


def strip_markdown_decoration(line: str) -> str:
    """Strip common markdown decoration from a line for verdict matching."""
    line = re.sub(r"[*_`]", "", line)
    line = re.sub(r"^[\s>#\-]*", "", line)
    return line.strip()


def parse_verdict(response_text: str) -> str:
    """Extract VERDICT: APPROVED|BLOCKING from a council response.

    Returns 'approved', 'blocking', or 'approved' (default if missing, with warning).
    """
    for line in reversed(response_text.strip().splitlines()):
        cleaned = strip_markdown_decoration(line)
        match = re.match(r"^VERDICT:\s*(APPROVED|BLOCKING)$", cleaned, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    # Missing verdict — treat as approved per design doc (log warning)
    return "approved"


def run_council_review(
    base: Path,
    branch: str,
    worktree: Path,
    ticket_path: Path,
    session_name: str,
    thread_id: str,
    start_sha: str | None,
    council_timeout: int,
    hand_mode: bool = False,
) -> tuple[str, list[str]]:
    """Run council review and return (outcome, feedback).

    outcome: 'approved', 'blocking', 'timeout', 'no_council'
    feedback: list of blocking feedback strings from councillors.
    """
    from kingdom.council.council import Council

    # Create council from config
    council = Council.create(base=base)
    if not council.members:
        logger.warning("No council members configured — skipping council review")
        return "no_council", []

    council.load_sessions(base, branch)

    # Build review prompt — worktree mode uses three-dot diff against feature branch
    ticket = read_ticket(ticket_path)
    feature_branch = None if hand_mode else branch
    diff = get_diff(worktree, start_sha, feature_branch=feature_branch)
    worklog = extract_worklog(ticket_path)
    prompt = build_review_prompt(ticket.title, ticket.body, diff, worklog)

    # Write king's review request to thread
    add_message(base, branch, thread_id, from_="king", to="council", body=prompt)

    logger.info("Council review dispatched to %d members (timeout: %ds)", len(council.members), council_timeout)

    # Query council with timeout — this blocks until all respond or timeout
    start_time = time.monotonic()
    responses = council.query_to_thread(
        prompt=prompt,
        base=base,
        branch=branch,
        thread_id=thread_id,
    )
    elapsed = time.monotonic() - start_time

    council.save_sessions(base, branch)

    # Check for timeout (council.query_to_thread handles per-member timeouts,
    # but we also check wall-clock time)
    if elapsed >= council_timeout:
        logger.warning("Council review timed out after %.0fs", elapsed)
        return "timeout", []

    # Parse verdicts
    blocking_feedback = []
    for name, response in responses.items():
        if response.error:
            logger.warning("Council member %s errored: %s", name, response.error)
            continue

        verdict = parse_verdict(response.text)

        # Check if verdict line was actually present
        has_verdict_line = any(
            re.match(r"^VERDICT:\s*(APPROVED|BLOCKING)$", strip_markdown_decoration(line), re.IGNORECASE)
            for line in response.text.strip().splitlines()
        )
        if not has_verdict_line:
            logger.warning("Council member %s did not include a VERDICT line — treating as APPROVED", name)

        if verdict == "blocking":
            logger.info("Council member %s: BLOCKING", name)
            blocking_feedback.append(f"[{name}] {response.text}")
        else:
            logger.info("Council member %s: APPROVED", name)

    if blocking_feedback:
        return "blocking", blocking_feedback
    return "approved", []


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
    # Load agent config from config system
    from kingdom.config import load_config

    cfg = load_config(base)
    agent_def = cfg.agents.get(agent_name)
    if agent_def is None:
        logger.error("Unknown agent: %s", agent_name)
        return "failed"
    agent_config = resolve_agent(agent_name, agent_def)

    # Read peasant settings from config
    max_iterations = cfg.peasant.max_iterations
    agent_timeout = cfg.peasant.timeout

    # Resolve peasant phase prompt: agent-specific overrides global
    phase_prompt = agent_def.prompts.get("peasant", "") or cfg.prompts.peasant

    # Find ticket
    result = find_ticket(base, ticket_id)
    if result is None:
        logger.error("Ticket not found: %s", ticket_id)
        return "failed"
    _, ticket_path = result

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

    # Record start_sha on first run (for diff scoping in council review).
    if not agent_state.start_sha:
        try:
            sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=10,
            )
            if sha_result.returncode == 0:
                start_sha = sha_result.stdout.strip()
                update_agent_state(base, branch, session_name, start_sha=start_sha)
                logger.info("Recorded start_sha: %s", start_sha)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Could not record start_sha")

    final_status = "failed"

    for iteration in range(1, max_iterations + 1):
        if stop_requested:
            final_status = "stopped"
            logger.info("Stopping at iteration %d (signal received)", iteration)
            break

        # Update session: working
        now = datetime.now(UTC).isoformat()
        update_agent_state(
            base,
            branch,
            session_name,
            status="working",
            last_activity=now,
        )

        worklog = extract_worklog(ticket_path)

        # Check for new directives from the lead
        directives, last_seen_seq = get_new_directives(base, branch, thread_id, last_seen_seq)

        # Build prompt
        prompt = build_prompt(ticket_path, worklog, directives, iteration, max_iterations, phase_prompt)

        # Call backend
        cmd = build_command(agent_config, prompt, resume_id)
        logger.info("Calling backend: %s", " ".join(cmd[:3]) + "...")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=agent_timeout,
                cwd=worktree,
                stdin=subprocess.DEVNULL,
                env=clean_agent_env(role="peasant", agent_name=session_name),
            )
        except subprocess.TimeoutExpired:
            logger.error("Backend timed out after %ds", agent_timeout)
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
            # Guard: reject DONE if the agent hasn't made any actual changes
            agent_state = get_agent_state(base, branch, session_name)
            if not has_code_changes(worktree, agent_state.start_sha):
                logger.warning("Agent reports DONE but no code changes detected — rejecting")
                append_worklog(
                    ticket_path,
                    "DONE rejected — no code changes detected. Actually implement the changes before reporting DONE.",
                )
                continue

            # --- Council review phase ---
            # Transition ticket to in_review, session to awaiting_council
            ticket_obj = read_ticket(ticket_path)
            ticket_obj.status = "in_review"
            write_ticket(ticket_obj, ticket_path)

            now = datetime.now(UTC).isoformat()
            update_agent_state(
                base,
                branch,
                session_name,
                status="awaiting_council",
                last_activity=now,
            )

            agent_state = get_agent_state(base, branch, session_name)
            review_outcome, blocking_feedback = run_council_review(
                base=base,
                branch=branch,
                worktree=worktree,
                ticket_path=ticket_path,
                session_name=session_name,
                thread_id=thread_id,
                start_sha=agent_state.start_sha,
                council_timeout=cfg.council.timeout,
                hand_mode=agent_state.hand_mode,
            )

            if review_outcome == "no_council":
                # No council configured — go straight to needs_king_review
                final_status = "needs_king_review"
                append_worklog(ticket_path, "No council configured — awaiting king review")
                break

            if review_outcome == "timeout":
                # Council timed out — escalate to king
                final_status = "needs_king_review"
                append_worklog(ticket_path, "Council review timed out — escalating to king")
                break

            if review_outcome == "approved":
                final_status = "needs_king_review"
                append_worklog(ticket_path, "Council review: APPROVED — awaiting king review")
                break

            # Blocking feedback — check bounce limit
            bounce_count = agent_state.review_bounce_count + 1
            update_agent_state(base, branch, session_name, review_bounce_count=bounce_count)

            if bounce_count >= 3:
                # Escalate after 3 bounces
                final_status = "needs_king_review"
                append_worklog(
                    ticket_path,
                    f"Council review: BLOCKING (bounce {bounce_count}/3) — escalating to king",
                )
                logger.warning("Review bounce limit reached (%d), escalating to king", bounce_count)
                break

            # Bounce back to working — inject feedback as directives
            logger.info("Council review: BLOCKING (bounce %d/3), returning to working", bounce_count)
            append_worklog(ticket_path, f"Council review: BLOCKING (bounce {bounce_count}/3) — returning to working")

            # Revert ticket to in_progress, session to working
            ticket_obj = read_ticket(ticket_path)
            ticket_obj.status = "in_progress"
            write_ticket(ticket_obj, ticket_path)

            # Add blocking feedback as a directive message in the thread
            feedback_body = "## Council Review Feedback (BLOCKING)\n\n" + "\n\n---\n\n".join(blocking_feedback)
            try:
                add_message(base, branch, thread_id, from_="king", to=session_name, body=feedback_body)
            except FileNotFoundError:
                logger.warning("Could not write council feedback to thread %s", thread_id)

            # Continue the loop — agent will pick up feedback as directives
            continue
        elif status == "blocked":
            final_status = "blocked"
            logger.info("Agent reports BLOCKED")
            break
        # else: continue

    else:
        # Max iterations reached
        logger.warning("Max iterations (%d) reached", max_iterations)
        append_worklog(ticket_path, f"Max iterations ({max_iterations}) reached without completion")
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
