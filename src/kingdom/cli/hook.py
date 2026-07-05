"""Hook event handlers for Claude Code integration.

The ``kd hook run`` subcommand reads a JSON payload from stdin, dispatches to
the appropriate handler based on ``hook_event_name``, and writes any response
JSON to stdout.  It is designed to be invoked by Claude Code as the hook
command registered in ``.claude/settings.json``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import typer

from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    find_project_root,
    normalize_branch_name,
    read_terminal_ticket_context,
    resolve_current_run,
)
from kingdom.ticket import read_ticket

hook_app = typer.Typer(name="hook", help="Claude Code hook handlers (internal).")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_START_BRIEF = (
    "KINGDOM WORKFLOW: You are working in a project managed by the kd CLI."
    " Before coding or research, ensure work is tracked with a ticket.\n"
    " 1. TICKET FIRST — King says something? Ask yourself: does this need a"
    " ticket? Bug, idea, complaint, scope change → kd tk create immediately.\n"
    " 2. LOG PROACTIVELY — Decision made, root cause found, scope changed,"
    " work completed → kd tk log. The King should never have to ask.\n"
    " 3. MOVE vs CREATE — Work belongs elsewhere → kd tk move. New problem"
    " noticed → kd tk create --backlog."
)

USER_PROMPT_REMINDER = (
    "Kingdom: keep the ticket accurate (body/AC/status/worklog)."
    " Prefer the last ticket started in this terminal with `kd tk start` when logging."
    " Requirement or acceptance-criteria change -> edit ticket markdown now."
    " Work/findings -> kd tk log. New bug/scope -> kd tk create|move."
)

WORK_TOOLS = {"WebSearch", "WebFetch", "Edit", "Write"}

STALE_TTL_SECONDS = 86400  # 24 hours

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def runtime_dir(project_dir: str | None = None) -> Path:
    """Return the .kd/runtime directory, creating it if needed."""
    base = Path(project_dir) if project_dir else Path(".")
    d = base / ".kd" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_file_for(project_dir: str | None, session_id: str) -> Path:
    """Return the turn-state file path for a given session."""
    return runtime_dir(project_dir) / f"turn-{session_id}.json"


def read_turn_state(path: Path) -> dict | None:
    """Read turn state, returning None on any error (fail-open)."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_turn_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state))


def tool_file_path(data: dict) -> str | None:
    file_path = data.get("tool_input", {}).get("file_path")
    if isinstance(file_path, str) and file_path:
        return file_path
    return None


def is_ticket_markdown_path(file_path: str, project_dir: str | None) -> bool:
    path = Path(file_path)
    if not path.is_absolute():
        base = Path(project_dir) if project_dir else Path(".")
        path = base / path

    path = path.resolve(strict=False)
    return path.suffix == ".md" and path.parent.name == "tickets" and ".kd" in path.parts


def is_ticket_markdown_tool_use(data: dict, project_dir: str | None) -> bool:
    file_path = tool_file_path(data)
    return file_path is not None and is_ticket_markdown_path(file_path, project_dir)


def ticket_paths_for_terminal_context(base: Path, ticket_id: str, feature: str, location: str | None) -> list[Path]:
    if location == "backlog":
        tickets_dir = backlog_root(base) / "tickets"
    elif location and location.startswith("archive:"):
        tickets_dir = archive_root(base) / location.removeprefix("archive:") / "tickets"
    elif location and location.startswith("branch:"):
        tickets_dir = branch_root(base, location.removeprefix("branch:")) / "tickets"
    else:
        tickets_dir = branch_root(base, feature) / "tickets"

    return [tickets_dir / f"{ticket_id}.md", tickets_dir / f"kin-{ticket_id}.md"]


def terminal_context_ticket_is_current(base: Path, ticket_id: str, feature: str, location: str | None = None) -> bool:
    candidate_paths = ticket_paths_for_terminal_context(base, ticket_id, feature, location)
    for ticket_path in candidate_paths:
        try:
            ticket = read_ticket(ticket_path)
        except (FileNotFoundError, ValueError, OSError):
            continue
        return (
            ticket.id == ticket_id
            and ticket.status == "in_progress"
            and not (ticket.assignee or "").startswith("peasant-")
        )
    return False


def terminal_context_base(project_dir: str | None) -> Path:
    fallback = Path(project_dir) if project_dir else Path(".")
    try:
        return find_project_root(fallback)
    except ValueError:
        return fallback


def find_stop_ticket_id(project_dir: str | None, session_id: str) -> str | None:
    base = terminal_context_base(project_dir)
    terminal_context = read_terminal_ticket_context(base, session_id=session_id)
    if terminal_context:
        try:
            current_feature = normalize_branch_name(resolve_current_run(base))
        except (RuntimeError, ValueError):
            current_feature = None
        ticket_id = terminal_context["ticket_id"]
        if (
            current_feature
            and terminal_context.get("feature") == current_feature
            and terminal_context_ticket_is_current(
                base,
                ticket_id,
                current_feature,
                terminal_context.get("location"),
            )
        ):
            return ticket_id

    try:
        proc = subprocess.run(
            ["kd", "tk", "current", "--id", "--exclude-peasant"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ticket_id = proc.stdout.strip()
        if proc.returncode != 0 or not ticket_id:
            return None
        return ticket_id
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Event handlers — each returns a string to print to stdout (or empty).
# ---------------------------------------------------------------------------


def handle_session_start(data: dict) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": SESSION_START_BRIEF,
            }
        }
    )


def handle_user_prompt_submit(data: dict) -> str:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    session_id = data.get("session_id", "")

    if session_id:
        sf = state_file_for(project_dir, session_id)
        write_turn_state(sf, {"had_work": False, "did_log": False})

        # TTL cleanup: remove stale turn-state files.
        cutoff = time.time() - STALE_TTL_SECONDS
        rd = runtime_dir(project_dir)
        for f in rd.glob("turn-*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass

    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": USER_PROMPT_REMINDER,
            }
        }
    )


def handle_post_tool_use(data: dict) -> str:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    session_id = data.get("session_id", "")
    if not session_id:
        return ""

    sf = state_file_for(project_dir, session_id)
    state = read_turn_state(sf)
    if state is None:
        return ""

    tool = data.get("tool_name", "")

    if tool in WORK_TOOLS and not is_ticket_markdown_tool_use(data, project_dir):
        state["had_work"] = True

    if tool == "Bash":
        cmd = data.get("tool_input", {}).get("command", "")
        if "kd tk log" in cmd or "kd ticket log" in cmd:
            state["did_log"] = True

    write_turn_state(sf, state)
    return ""


def handle_stop(data: dict) -> str:
    # If stop_hook_active is set, another stop handler is running — bail.
    if data.get("stop_hook_active", False):
        return ""

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    session_id = data.get("session_id", "")
    if not session_id:
        return ""

    sf = state_file_for(project_dir, session_id)
    state = read_turn_state(sf)
    if state is None:
        return ""

    if not (state.get("had_work") and not state.get("did_log")):
        return ""

    # Check for an active ticket (fail-open on any error).
    ticket_id = find_stop_ticket_id(project_dir, session_id)
    if not ticket_id:
        return ""  # Timeout or error — fail open.

    result = {
        "decision": "block",
        "reason": (
            f"KINGDOM: You did meaningful work this turn but didn't log it."
            f" Run: kd tk log {ticket_id} 'summary of what you did'"
        ),
    }
    return json.dumps(result)


# Map event names to handlers.
HANDLERS = {
    "SessionStart": handle_session_start,
    "UserPromptSubmit": handle_user_prompt_submit,
    "PostToolUse": handle_post_tool_use,
    "Stop": handle_stop,
}

# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@hook_app.command("run", help="Process a Claude Code hook event from stdin.")
def hook_run() -> None:
    """Read hook payload JSON from stdin, dispatch by event, write response."""
    # Bypass all processing if requested.
    if os.environ.get("KD_HOOK_BYPASS") == "1":
        return

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return  # Fail open on bad input.

    event = data.get("hook_event_name", "")
    handler = HANDLERS.get(event)
    if handler is None:
        return  # Unknown event — silent.

    try:
        output = handler(data)
    except Exception:
        return  # Fail open on handler errors.

    if output:
        typer.echo(output)
