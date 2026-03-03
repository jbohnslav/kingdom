"""Autonomous agent harness for peasant execution.

The harness runs an autonomous loop:
  1. Build prompt (ticket + acceptance criteria + worklog + new directives)
  2. Call backend CLI (agent commits its own changes)
  3. Parse response
  4. Append to worklog in ticket
  5. Update session file (status, resume_id, last_activity)
  6. Write response as message to work thread
  7. Check stop conditions: done, blocked, stopped, failed

Called by ``python -m kingdom.worker`` (spawned by peasant start).
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
    *,
    worktree: Path | None = None,
    repo_root: Path | None = None,
    ticket_id: str = "",
    ticket_title: str = "",
) -> str:
    """Build the prompt sent to the backend agent.

    References the ticket file by path (so the agent can read it directly)
    and includes existing worklog plus new directives and environment anchors.
    """
    parts = []

    if phase_prompt:
        parts.append(phase_prompt)
        parts.append("")

    # --- Identity and context ---
    parts.append(
        "You are a peasant — an autonomous coding agent in Kingdom (kd). "
        "Kingdom is a ticket-driven development workflow: the King assigns tickets, "
        "peasants implement them, and the council reviews the result. "
        "If the council blocks your work, you'll get their feedback and another chance to fix it."
    )

    # --- Where you are ---
    if worktree:
        parts.append("")
        parts.append(
            f"You are working in an isolated git worktree at {worktree} "
            f"on branch ticket/{ticket_id}. All your edits, commits, and commands "
            f"should happen here — don't cd to {repo_root or 'the parent repo'} "
            f"or work outside this directory."
        )

    # --- The ticket ---
    parts.append("")
    parts.append(f"Your ticket is at {ticket_path}.")
    if ticket_title:
        parts.append(f'It\'s called "{ticket_title}."')
    parts.append(
        "Read it carefully before you start, especially the acceptance criteria — "
        "those are what the council will judge your work against."
    )

    if worklog:
        parts.append("")
        parts.append("Here's the worklog so far:")
        parts.append(worklog)

    if directives:
        parts.append("")
        parts.append("The King has given you these directives:")
        for d in directives:
            parts.append(f"- {d}")

    # --- How to work ---
    parts.append("")
    parts.append(f"This is iteration {iteration} of {max_iterations}.")
    if iteration > 1:
        parts.append(
            "You've been bounced back — the council had feedback on your last attempt. "
            "Focus on what they flagged before doing anything else."
        )
    parts.append("")
    parts.append(
        "Read the relevant source code before changing it. Make minimal, correct changes. "
        "Commit as you go with descriptive messages."
    )
    parts.append("")
    if ticket_id:
        parts.append(
            "Keep the ticket worklog updated as you work. Log important decisions, "
            "tradeoffs, things you noticed, or King input using "
            f'`kd tk log {ticket_id} "message"` or by editing the ticket file directly. '
            "The worklog is how the King stays informed about what you're doing and why."
        )
    else:
        parts.append(
            "Keep the ticket worklog updated as you work. Log important decisions, "
            "tradeoffs, and things you noticed. The worklog is how the King stays "
            "informed about what you're doing and why."
        )
    parts.append("")
    parts.append(
        "Before reporting DONE, run the project's tests, linter, "
        "and pre-commit hooks. Everything must pass. If you haven't actually changed any code "
        "or made any commits, you're not done — don't claim DONE with nothing to show. "
        "Exception: if the work is genuinely complete without code changes "
        "(e.g., the fix was already applied, or the ticket only required verification), "
        "you may report DONE and explain why no changes were needed."
    )
    parts.append("")
    parts.append(
        "If you're stuck or need a decision from the King, report BLOCKED with a clear "
        "explanation of what you need. Don't spin — it's better to ask than to waste iterations."
    )

    # --- Response format ---
    parts.append("")
    parts.append(
        "When you respond, start with a plain prose paragraph summarizing what you changed. "
        "Be concrete — name the files, describe the behavior change, explain what you fixed. "
        'No headings, no numbered list, no labels like "What I did this iteration." '
        "This paragraph shows up directly in `kd peasant watch`, so make it useful."
    )
    parts.append("")
    parts.append("End your response with exactly one status line:\nSTATUS: DONE\nSTATUS: BLOCKED\nSTATUS: CONTINUE")

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

    Takes the first substantive paragraph before the STATUS line,
    skipping bare markdown headings (``## …``) that contain no content.
    """
    lines = []
    for line in response_text.strip().splitlines():
        if re.match(r"^STATUS:\s*(DONE|BLOCKED|CONTINUE)$", line.strip(), re.IGNORECASE):
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    # Take first substantive paragraph, skipping bare headings
    paragraphs = text.split("\n\n")
    entry = ""
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        # Skip standalone markdown headings (e.g. "## What I did this iteration")
        if re.match(r"^#{1,6}\s+\S", stripped) and "\n" not in stripped:
            continue
        if is_placeholder_worklog_paragraph(stripped):
            continue
        entry = stripped
        break
    if len(entry) > 300:
        entry = entry[:297] + "..."
    return entry


def format_worklog_timestamp(dt: datetime) -> str:
    """Format a worklog timestamp in local time.

    Returns "[HH:MM]" for today's entries, "[YYYY-MM-DD HH:MM]" for older ones.
    All times are converted to local timezone so they align with worktree
    poll timestamps in ``kd peasant watch``.
    """
    local_dt = dt.astimezone()
    today = datetime.now().astimezone().date()
    if local_dt.date() == today:
        return f"[{local_dt.strftime('%H:%M')}]"
    return f"[{local_dt.strftime('%Y-%m-%d %H:%M')}]"


def append_worklog(ticket_path: Path, entry: str) -> None:
    now = datetime.now(UTC)
    append_worklog_entry(ticket_path, entry, timestamp=now, timestamp_text=format_worklog_timestamp(now))


def is_placeholder_worklog_paragraph(paragraph: str) -> bool:
    """Return True when *paragraph* is just a section label with no content."""
    if "\n" in paragraph:
        return False

    normalized = strip_markdown_decoration(paragraph)
    normalized = re.sub(r"^\d+[.)]\s*", "", normalized)
    normalized = normalized.rstrip(":").strip().lower()
    return normalized in {
        "what i did this iteration",
        "what you did this iteration",
        "summary",
        "details",
    }


def summarize_feedback(feedback: list[str], max_chars: int = 500) -> str:
    """Summarize council feedback for worklog entries.

    Takes each "[name] response_text" entry, extracts the name and truncates
    the response to the first line / max_chars for a compact worklog summary.
    """
    lines = []
    for entry in feedback:
        # Extract [name] prefix
        if entry.startswith("["):
            bracket_end = entry.index("]") + 1
            name_part = entry[:bracket_end]
            text = entry[bracket_end:].strip()
        else:
            name_part = ""
            text = entry.strip()

        verdict = parse_verdict(text).upper()
        summary = ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^VERDICT:\s*(APPROVED|BLOCKING)$", strip_markdown_decoration(stripped), re.IGNORECASE):
                continue
            summary = stripped
            break

        if summary:
            prefix = f"{verdict}: "
            if len(prefix) + len(summary) > max_chars:
                available = max_chars - len(prefix) - 3
                if available > 0:
                    summary = summary[:available] + "..."
                else:
                    summary = verdict[: max_chars - 3] + "..."
                    lines.append(f"{name_part} {summary}" if name_part else summary)
                    continue
            summary = f"{prefix}{summary}"
        else:
            summary = verdict
        lines.append(f"{name_part} {summary}" if name_part else summary)
    return "\n".join(lines)


def get_diff_stat(worktree: Path, since: str | None = None) -> str | None:
    """Run git diff --stat in the worktree and return the output.

    When *since* is given, diffs committed changes ``since..HEAD``.
    Otherwise falls back to uncommitted changes (HEAD then index).

    Returns None if there are no changes or on error.
    """
    try:
        if since:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{since}..HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        # Uncommitted changes (staged + unstaged vs HEAD)
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


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


def run_streaming_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    live_log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with real-time stdout/stderr streaming.

    Pipes stdout and stderr, writing each line to *live_log_path* in real time
    while accumulating full buffers for the returned ``CompletedProcess``.
    This gives ``parse_response()`` the same interface as ``subprocess.run()``
    while making output visible to ``peasant watch`` during execution.
    """
    live_log_path.parent.mkdir(parents=True, exist_ok=True) if live_log_path else None

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

    def drain(stream, buf: list[str], label: str) -> None:
        for line in stream:
            buf.append(line)
            if live_log_path:
                try:
                    with live_log_path.open("a", encoding="utf-8") as f:
                        f.write(line)
                except OSError:
                    pass

    stdout_thread = threading.Thread(target=drain, args=(proc.stdout, stdout_lines, "stdout"), daemon=True)
    stderr_thread = threading.Thread(target=drain, args=(proc.stderr, stderr_lines, "stderr"), daemon=True)
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


def check_worktree_branch(worktree: Path, expected_branch: str) -> bool:
    """Verify the worktree HEAD is on the expected branch.

    Returns True if the branch matches (or if git fails — don't block on
    infra errors). Returns False if the branch has changed, meaning the
    agent escaped.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("Could not check worktree branch (git returned %d)", result.returncode)
            return True  # Don't block on git failures
        actual = result.stdout.strip()
        if actual != expected_branch:
            logger.error(
                "BRANCH ESCAPE: worktree HEAD is on '%s', expected '%s'",
                actual,
                expected_branch,
            )
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("Could not check worktree branch (timeout/not found)")
        return True  # Don't block on infra errors


def get_changed_files(worktree: Path, start_sha: str | None, feature_branch: str | None = None) -> str:
    """Get the list of changed files (--stat format) for review context.

    Uses the same ref resolution logic as the old get_diff — three-dot for
    worktree mode, two-dot for hand mode, HEAD fallback otherwise.
    """
    try:
        if feature_branch:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{feature_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=30,
            )
            if result.returncode != 0 and start_sha:
                result = subprocess.run(
                    ["git", "diff", "--stat", f"{start_sha}..HEAD"],
                    capture_output=True,
                    text=True,
                    cwd=worktree,
                    timeout=30,
                )
        elif start_sha:
            result = subprocess.run(
                ["git", "diff", "--stat", f"{start_sha}..HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=30,
            )
        else:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=30,
            )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "(no changes detected)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(could not generate file list)"


def get_commit_log(worktree: Path, start_sha: str | None, feature_branch: str | None = None) -> str:
    """Get the oneline commit log for review context."""
    try:
        if feature_branch:
            ref_range = f"{feature_branch}..HEAD"
        elif start_sha:
            ref_range = f"{start_sha}..HEAD"
        else:
            ref_range = "HEAD~10..HEAD"
        result = subprocess.run(
            ["git", "log", "--oneline", ref_range],
            capture_output=True,
            text=True,
            cwd=worktree,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def build_review_prompt(
    *,
    changed_files: str,
    base_branch: str = "",
    branch: str = "",
    commits: str = "",
    ticket_title: str = "",
    ticket_body: str = "",
    ticket_path: str = "",
    worklog: str = "",
) -> str:
    """Build the shared agent-facing review prompt.

    Used by both the harness council review and ``kd council review``.
    Does NOT paste the full diff — points reviewers at the code and lets
    them investigate with git commands.

    Per-agent and global ``prompts.review`` config is handled by the
    ``CouncilMember.phase_prompt`` mechanism — it gets prepended
    automatically when the member builds its command.
    """
    parts = ["## Code Review Request", ""]

    if ticket_title:
        parts.append(f"**Ticket:** {ticket_title}")
        if ticket_path:
            parts.append(f"**Ticket path:** {ticket_path}")
        parts.append("")
        body = ticket_body.split("## Worklog")[0].strip() if "## Worklog" in ticket_body else ticket_body.strip()
        if body:
            parts.extend(["### Ticket Description", body, ""])

    if worklog:
        parts.extend(["### Worklog", worklog, ""])

    if branch:
        parts.append(f"**Branch:** {branch}")
    if base_branch:
        parts.append(f"**Base:** {base_branch}")
    if branch or base_branch:
        parts.append("")

    if commits:
        parts.extend(["### Commits", f"```\n{commits}\n```", ""])

    parts.extend(["### Changed Files", f"```\n{changed_files}\n```", ""])

    parts.extend(
        [
            "### How to Review",
            "You are a coding agent — inspect the code yourself. Suggested commands:",
        ]
    )
    if base_branch:
        parts.append(f"- `git diff {base_branch}...HEAD` — full diff")
        parts.append(f"- `git log --oneline {base_branch}..HEAD` — commit history")
    else:
        parts.append("- `git diff HEAD~N` or `git log --oneline` — inspect recent changes")
    if ticket_path:
        parts.append(f"- `cat {ticket_path}` — read the full ticket")
    parts.append("- Read individual changed files to understand context")
    parts.append("")

    parts.extend(
        [
            "### Review Standard",
            "- Correctness: does it do what the ticket asks?",
            "- Edge cases: are there unhandled scenarios?",
            "- Code quality: is it readable, maintainable, and well-structured?",
            "- Tests: are changes adequately tested? Run the project's test suite and linter to verify.",
            "- Regressions: could this break existing behavior?",
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

    Returns 'approved', 'blocking', or 'unknown' (if no VERDICT line found).
    """
    for line in reversed(response_text.strip().splitlines()):
        cleaned = strip_markdown_decoration(line)
        match = re.match(r"^VERDICT:\s*(APPROVED|BLOCKING)$", cleaned, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return "unknown"


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

    # Create council with review phase — resolves per-agent prompts.review
    council = Council.create(base=base, phase="review")
    if not council.members:
        logger.warning("No council members configured — skipping council review")
        return "no_council", []

    council.load_sessions(base, branch)

    # Build review prompt — point reviewers at code, don't paste full diff
    ticket = read_ticket(ticket_path)
    feature_branch = None if hand_mode else branch
    changed_files = get_changed_files(worktree, start_sha, feature_branch=feature_branch)
    commits = get_commit_log(worktree, start_sha, feature_branch=feature_branch)
    worklog = extract_worklog(ticket_path)
    prompt = build_review_prompt(
        changed_files=changed_files,
        base_branch=feature_branch or "",
        branch=branch,
        commits=commits,
        ticket_title=ticket.title,
        ticket_body=ticket.body,
        ticket_path=str(ticket_path),
        worklog=worklog,
    )

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

    # Parse verdicts — collect feedback from ALL members, not just blocking ones
    blocking_feedback = []
    all_feedback = []
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

        all_feedback.append(f"[{name}] {response.text}")
        if verdict == "blocking":
            logger.info("Council member %s: BLOCKING", name)
            blocking_feedback.append(f"[{name}] {response.text}")
        else:
            logger.info("Council member %s: APPROVED", name)

    if blocking_feedback:
        return "blocking", all_feedback
    return "approved", all_feedback


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

    # Resolve peasant phase prompt: agent-specific overrides global
    phase_prompt = agent_def.prompts.get("peasant", "") or cfg.prompts.peasant

    # Find ticket
    result = find_ticket(base, ticket_id)
    if result is None:
        logger.error("Ticket not found: %s", ticket_id)
        return "failed"
    _, ticket_path = result
    ticket_title = read_ticket(ticket_path).title

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

    # Determine expected branch for escape detection
    expected_branch = branch if agent_state.hand_mode else f"ticket/{ticket_id}"

    # Pre-loop sanity check: bail early if worktree is already on the wrong branch
    if not check_worktree_branch(worktree, expected_branch):
        append_worklog(
            ticket_path,
            f"BRANCH ESCAPE: worktree is not on expected branch '{expected_branch}' — aborting",
        )
        now = datetime.now(UTC).isoformat()
        update_agent_state(base, branch, session_name, status="failed", last_activity=now)
        return "failed"

    # Record start_sha on first run (for diff scoping in council review).
    # Must come after branch check so we don't record a SHA from the wrong branch.
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
    last_bounce_feedback: list[str] = []  # Council feedback from last bounce (for worklog context)

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

        # Iteration start entry with context about what the agent will work on
        if iteration == 1:
            append_worklog(
                ticket_path, f"Iteration {iteration}/{max_iterations} — calling agent\nTicket: {ticket_title}"
            )
        elif last_bounce_feedback:
            n_blocking = sum(1 for f in last_bounce_feedback if parse_verdict(f) == "blocking")
            n_total = len(last_bounce_feedback)
            append_worklog(
                ticket_path,
                f"Iteration {iteration}/{max_iterations} — calling agent\n"
                f"Bouncing on council feedback ({n_blocking} blocking, {n_total - n_blocking} approved) — see review above",
            )
            last_bounce_feedback = []
        else:
            append_worklog(ticket_path, f"Iteration {iteration}/{max_iterations} — calling agent")

        worklog = extract_worklog(ticket_path)

        # Check for new directives from the lead
        directives, last_seen_seq = get_new_directives(base, branch, thread_id, last_seen_seq)

        # Build prompt
        prompt = build_prompt(
            ticket_path,
            worklog,
            directives,
            iteration,
            max_iterations,
            phase_prompt,
            worktree=worktree,
            repo_root=base,
            ticket_id=ticket_id,
            ticket_title=ticket_title,
        )

        # Capture HEAD before agent call so we can diff committed changes after
        pre_iteration_sha = None
        try:
            sha_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=worktree,
                timeout=10,
            )
            if sha_proc.returncode == 0:
                pre_iteration_sha = sha_proc.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Call backend — streaming=True enables incremental NDJSON output
        # so agent-live.log gets data in real time for peasant watch to tail.
        cmd = build_command(agent_config, prompt, resume_id, streaming=True)
        logger.info("Calling backend: %s", " ".join(cmd[:3]) + "...")

        # Live agent log for `peasant watch` to tail during execution
        agent_live_log = logs_root(base, branch) / session_name / "agent-live.log"

        try:
            proc = run_streaming_subprocess(
                cmd,
                cwd=worktree,
                env=clean_agent_env(role="peasant", agent_name=session_name, kd_base=str(base)),
                live_log_path=agent_live_log,
            )
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

        # Post-iteration branch escape check
        if not check_worktree_branch(worktree, expected_branch):
            append_worklog(
                ticket_path,
                f"BRANCH ESCAPE detected after iteration {iteration}: "
                f"worktree is not on expected branch '{expected_branch}' — aborting",
            )
            final_status = "failed"
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

        diff_stat = get_diff_stat(worktree, since=pre_iteration_sha)
        worklog_entry = extract_worklog_entry(text)
        if worklog_entry:
            append_worklog(ticket_path, worklog_entry)

        # Append file change summary from git diff --stat
        if diff_stat:
            append_worklog(ticket_path, f"Files changed:\n{diff_stat}")

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
            # Note if no code changes detected, but let it proceed — some
            # tickets are genuinely complete without code changes.
            agent_state = get_agent_state(base, branch, session_name)
            if not has_code_changes(worktree, agent_state.start_sha):
                logger.info("Agent reports DONE with no code changes — proceeding to review")
                append_worklog(ticket_path, "DONE with no code changes — proceeding to council review.")

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
            review_outcome, review_feedback = run_council_review(
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
                feedback_summary = summarize_feedback(review_feedback)
                msg = "Council review: APPROVED — awaiting king review"
                if feedback_summary:
                    msg += f"\n{feedback_summary}"
                append_worklog(ticket_path, msg)
                break

            # Blocking feedback — check bounce limit
            bounce_count = agent_state.review_bounce_count + 1
            update_agent_state(base, branch, session_name, review_bounce_count=bounce_count)

            feedback_summary = summarize_feedback(review_feedback)

            if bounce_count >= 3:
                # Escalate after 3 bounces
                final_status = "needs_king_review"
                msg = f"Council review: BLOCKING (bounce {bounce_count}/3) — escalating to king"
                if feedback_summary:
                    msg += f"\n{feedback_summary}"
                append_worklog(ticket_path, msg)
                logger.warning("Review bounce limit reached (%d), escalating to king", bounce_count)
                break

            # Bounce back to working — inject feedback as directives
            logger.info("Council review: BLOCKING (bounce %d/3), returning to working", bounce_count)
            msg = f"Council review: BLOCKING (bounce {bounce_count}/3) — returning to working"
            if feedback_summary:
                msg += f"\n{feedback_summary}"
            append_worklog(ticket_path, msg)

            # Save blocking feedback for next iteration's worklog context
            last_bounce_feedback = review_feedback

            # Revert ticket to in_progress, session to working
            ticket_obj = read_ticket(ticket_path)
            ticket_obj.status = "in_progress"
            write_ticket(ticket_obj, ticket_path)

            # Add blocking feedback as a directive message in the thread
            # Filter to blocking members only for the peasant directive
            blocking_only = [f for f in review_feedback if parse_verdict(f) == "blocking"]
            feedback_body = "## Council Review Feedback (BLOCKING)\n\n" + "\n\n---\n\n".join(
                blocking_only or review_feedback
            )
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
