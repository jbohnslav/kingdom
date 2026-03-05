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
    "Kingdom: create or update a ticket? (kd tk create|move|log)."
    " King decision? Log it. Finished work item? Log it. Found a bug? Ticket it."
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


# ---------------------------------------------------------------------------
# Event handlers — each returns a string to print to stdout (or empty).
# ---------------------------------------------------------------------------


def handle_session_start(data: dict) -> str:
    return SESSION_START_BRIEF


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

    return USER_PROMPT_REMINDER


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

    if tool in WORK_TOOLS:
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
    try:
        proc = subprocess.run(
            ["kd", "tk", "current", "--id"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ticket_id = proc.stdout.strip()
        if proc.returncode != 0 or not ticket_id:
            return ""  # No active ticket — fail open.
    except Exception:
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
