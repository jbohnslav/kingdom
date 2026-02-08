"""Agent session state management.

Per-agent runtime state stored in ``sessions/<agent>.json`` under each branch.
Each agent writes only its own file, so no locking is needed.

Session JSON format::

    {
        "status": "idle",
        "resume_id": "abc123",
        "pid": null,
        "ticket": null,
        "thread": null,
        "started_at": null,
        "last_activity": null
    }

Agent status values: idle, working, blocked, done, failed, stopped.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kingdom.state import branch_root, read_json, sessions_root, write_json

AGENT_STATUSES = frozenset({"idle", "working", "blocked", "done", "failed", "stopped"})


@dataclass
class AgentState:
    """Runtime state for a single agent."""

    name: str
    status: str = "idle"
    resume_id: str | None = None
    pid: int | None = None
    ticket: str | None = None
    thread: str | None = None
    started_at: str | None = None
    last_activity: str | None = None


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def session_path(base: Path, branch: str, agent_name: str) -> Path:
    """Return path to sessions/<agent>.json for a branch."""
    return sessions_root(base, branch) / f"{agent_name}.json"


def legacy_session_path(base: Path, branch: str, agent_name: str) -> Path:
    """Return path to legacy sessions/<agent>.session file."""
    return sessions_root(base, branch) / f"{agent_name}.session"


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def get_agent_state(base: Path, branch: str, agent_name: str) -> AgentState:
    """Read agent state from sessions/<agent>.json.

    If a legacy ``.session`` file exists and no ``.json`` file exists,
    migrates automatically (reads resume_id, writes new format, removes old file).

    Returns default idle state if no session file exists.
    """
    json_path = session_path(base, branch, agent_name)
    old_path = legacy_session_path(base, branch, agent_name)

    # Migrate legacy .session file if needed
    if not json_path.exists() and old_path.exists():
        resume_id = old_path.read_text(encoding="utf-8").strip()
        state = AgentState(name=agent_name, resume_id=resume_id or None)
        set_agent_state(base, branch, agent_name, state)
        old_path.unlink()
        return state

    if not json_path.exists():
        return AgentState(name=agent_name)

    data = read_json(json_path)
    return AgentState(
        name=data.get("name", agent_name),
        status=data.get("status", "idle"),
        resume_id=data.get("resume_id"),
        pid=data.get("pid"),
        ticket=data.get("ticket"),
        thread=data.get("thread"),
        started_at=data.get("started_at"),
        last_activity=data.get("last_activity"),
    )


def set_agent_state(base: Path, branch: str, agent_name: str, state: AgentState) -> None:
    """Write agent state to sessions/<agent>.json."""
    json_path = session_path(base, branch, agent_name)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    state.name = agent_name
    data: dict[str, Any] = {}
    for key, value in asdict(state).items():
        if value is not None:
            data[key] = value

    write_json(json_path, data)


def update_agent_state(base: Path, branch: str, agent_name: str, **fields: Any) -> AgentState:
    """Read-modify-write agent state with the given field updates.

    Convenience wrapper: reads current state, applies updates, writes back.

    Returns:
        Updated AgentState.
    """
    state = get_agent_state(base, branch, agent_name)

    for key, value in fields.items():
        if not hasattr(state, key):
            raise ValueError(f"Unknown AgentState field: {key}")
        setattr(state, key, value)

    set_agent_state(base, branch, agent_name, state)
    return state


def list_active_agents(base: Path, branch: str) -> list[AgentState]:
    """Return all agents with status != idle.

    Scans sessions/<agent>.json files in the branch sessions directory.
    """
    sdir = sessions_root(base, branch)
    if not sdir.exists():
        return []

    active: list[AgentState] = []
    for path in sorted(sdir.glob("*.json")):
        agent_name = path.stem
        try:
            state = get_agent_state(base, branch, agent_name)
        except (FileNotFoundError, KeyError):
            continue
        if state.status != "idle":
            active.append(state)

    return active


# ---------------------------------------------------------------------------
# Current thread pointer (in state.json)
# ---------------------------------------------------------------------------


def get_current_thread(base: Path, branch: str) -> str | None:
    """Read current_thread from branch state.json."""
    state_path = branch_root(base, branch) / "state.json"
    try:
        data = read_json(state_path)
    except FileNotFoundError:
        return None
    return data.get("current_thread")


def set_current_thread(base: Path, branch: str, thread_id: str | None) -> None:
    """Set current_thread in branch state.json, preserving other fields."""
    state_path = branch_root(base, branch) / "state.json"
    try:
        data = read_json(state_path)
    except FileNotFoundError:
        data = {}

    if thread_id is None:
        data.pop("current_thread", None)
    else:
        data["current_thread"] = thread_id

    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(state_path, data)
