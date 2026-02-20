"""Agent session state management.

Per-agent runtime state stored in ``sessions/<agent>.json`` under each branch.
Read-modify-write helpers use ``fcntl.flock`` advisory locking so that
concurrent callers (harness process, CLI commands) do not lose updates.

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

Agent status values: idle, working, blocked, done, failed, stopped,
awaiting_council, needs_king_review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kingdom.state import branch_root, locked_json_update, read_json, sessions_root, write_json

AGENT_STATUSES = frozenset(
    {
        "idle",
        "working",
        "blocked",
        "done",
        "failed",
        "stopped",
        "awaiting_council",
        "needs_king_review",
    }
)


@dataclass
class AgentState:
    """Runtime state for a single agent."""

    name: str
    status: str = "idle"
    resume_id: str | None = None
    pid: int | None = None
    ticket: str | None = None
    thread: str | None = None
    agent_backend: str | None = None
    started_at: str | None = None
    last_activity: str | None = None
    start_sha: str | None = None
    review_bounce_count: int = 0
    hand_mode: bool = False


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


def agent_state_from_dict(data: dict[str, Any], name: str) -> AgentState:
    """Reconstruct AgentState from a persisted JSON dict, filling defaults for missing keys."""
    return AgentState(
        name=data.get("name", name),
        status=data.get("status", "idle"),
        resume_id=data.get("resume_id"),
        pid=data.get("pid"),
        ticket=data.get("ticket"),
        thread=data.get("thread"),
        agent_backend=data.get("agent_backend"),
        started_at=data.get("started_at"),
        last_activity=data.get("last_activity"),
        start_sha=data.get("start_sha"),
        review_bounce_count=data.get("review_bounce_count", 0),
        hand_mode=data.get("hand_mode", False),
    )


def agent_state_to_dict(state: AgentState) -> dict[str, Any]:
    """Serialize AgentState to a dict, dropping None values."""
    return {k: v for k, v in asdict(state).items() if v is not None}


def get_agent_state(base: Path, branch: str, agent_name: str) -> AgentState:
    """Read agent state, migrating legacy .session files if needed.

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

    return agent_state_from_dict(read_json(json_path), agent_name)


def set_agent_state(base: Path, branch: str, agent_name: str, state: AgentState) -> None:
    json_path = session_path(base, branch, agent_name)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    state.name = agent_name
    write_json(json_path, agent_state_to_dict(state))


def update_agent_state(base: Path, branch: str, agent_name: str, **fields: Any) -> AgentState:
    """Read-modify-write agent state under exclusive file lock.

    Concurrent callers (harness, CLI) won't interleave and lose updates.
    """
    dummy = AgentState(name=agent_name)
    for key in fields:
        if not hasattr(dummy, key):
            raise ValueError(f"Unknown AgentState field: {key}")

    json_path = session_path(base, branch, agent_name)

    def apply_fields(data: dict[str, Any]) -> dict[str, Any]:
        state = agent_state_from_dict(data, agent_name)
        for key, value in fields.items():
            setattr(state, key, value)
        state.name = agent_name
        return agent_state_to_dict(state)

    data = locked_json_update(json_path, apply_fields)
    return agent_state_from_dict(data, agent_name)


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
    """Set current_thread in branch state.json, preserving other fields.

    Uses file locking to avoid losing concurrent updates to other fields
    in the same state.json (e.g. ``design_approved``, ``branch``).
    """
    state_path = branch_root(base, branch) / "state.json"

    def apply_thread(data: dict[str, Any]) -> dict[str, Any]:
        if thread_id is None:
            data.pop("current_thread", None)
        else:
            data["current_thread"] = thread_id
        return data

    locked_json_update(state_path, apply_thread)
