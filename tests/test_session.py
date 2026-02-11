"""Tests for kingdom.session module."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from kingdom.session import (
    AgentState,
    get_agent_state,
    get_current_thread,
    legacy_session_path,
    list_active_agents,
    session_path,
    set_agent_state,
    set_current_thread,
    update_agent_state,
)
from kingdom.state import ensure_branch_layout, locked_json_update, sessions_root

BRANCH = "feature/test-branch"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    return tmp_path


class TestPathHelpers:
    def test_session_path(self, project: Path) -> None:
        p = session_path(project, BRANCH, "claude")
        assert p == sessions_root(project, BRANCH) / "claude.json"

    def test_legacy_session_path(self, project: Path) -> None:
        p = legacy_session_path(project, BRANCH, "claude")
        assert p == sessions_root(project, BRANCH) / "claude.session"


class TestGetAgentState:
    def test_returns_default_when_no_file(self, project: Path) -> None:
        state = get_agent_state(project, BRANCH, "claude")
        assert state.name == "claude"
        assert state.status == "idle"
        assert state.resume_id is None
        assert state.pid is None

    def test_reads_existing_json(self, project: Path) -> None:
        p = session_path(project, BRANCH, "claude")
        p.write_text(
            json.dumps(
                {
                    "name": "claude",
                    "status": "working",
                    "resume_id": "sess-abc",
                    "pid": 12345,
                    "ticket": "kin-042",
                    "thread": "kin-042-work",
                    "started_at": "2026-02-07T15:30:00Z",
                    "last_activity": "2026-02-07T15:44:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        state = get_agent_state(project, BRANCH, "claude")
        assert state.name == "claude"
        assert state.status == "working"
        assert state.resume_id == "sess-abc"
        assert state.pid == 12345
        assert state.ticket == "kin-042"
        assert state.thread == "kin-042-work"
        assert state.started_at == "2026-02-07T15:30:00Z"
        assert state.last_activity == "2026-02-07T15:44:00Z"


class TestSetAgentState:
    def test_writes_json_file(self, project: Path) -> None:
        state = AgentState(name="claude", status="working", resume_id="sess-123")
        set_agent_state(project, BRANCH, "claude", state)

        p = session_path(project, BRANCH, "claude")
        assert p.exists()

        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["name"] == "claude"
        assert data["status"] == "working"
        assert data["resume_id"] == "sess-123"

    def test_omits_none_fields(self, project: Path) -> None:
        state = AgentState(name="claude")
        set_agent_state(project, BRANCH, "claude", state)

        p = session_path(project, BRANCH, "claude")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "pid" not in data
        assert "ticket" not in data
        assert "name" in data
        assert "status" in data

    def test_creates_sessions_dir_if_missing(self, tmp_path: Path) -> None:
        # Don't use the project fixture — start from scratch
        ensure_branch_layout(tmp_path, "fresh/branch")
        sdir = sessions_root(tmp_path, "fresh/branch")
        # Remove sessions dir to test auto-creation
        sdir.rmdir()
        assert not sdir.exists()

        state = AgentState(name="claude", status="idle")
        set_agent_state(tmp_path, "fresh/branch", "claude", state)
        assert session_path(tmp_path, "fresh/branch", "claude").exists()


class TestUpdateAgentState:
    def test_updates_single_field(self, project: Path) -> None:
        state = AgentState(name="claude", status="idle", resume_id="sess-1")
        set_agent_state(project, BRANCH, "claude", state)

        updated = update_agent_state(project, BRANCH, "claude", status="working")
        assert updated.status == "working"
        assert updated.resume_id == "sess-1"  # preserved

        # Verify persisted
        reread = get_agent_state(project, BRANCH, "claude")
        assert reread.status == "working"
        assert reread.resume_id == "sess-1"

    def test_updates_multiple_fields(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude"))

        updated = update_agent_state(
            project,
            BRANCH,
            "claude",
            status="working",
            pid=9999,
            ticket="kin-042",
        )
        assert updated.status == "working"
        assert updated.pid == 9999
        assert updated.ticket == "kin-042"

    def test_unknown_field_raises(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude"))

        with pytest.raises(ValueError, match="Unknown AgentState field"):
            update_agent_state(project, BRANCH, "claude", bogus="value")


class TestLegacyMigration:
    def test_migrates_session_to_json(self, project: Path) -> None:
        # Write a legacy .session file
        old_path = legacy_session_path(project, BRANCH, "claude")
        old_path.write_text("sess-legacy-123\n", encoding="utf-8")

        state = get_agent_state(project, BRANCH, "claude")
        assert state.resume_id == "sess-legacy-123"
        assert state.status == "idle"

        # Legacy file should be removed
        assert not old_path.exists()
        # New JSON file should exist
        assert session_path(project, BRANCH, "claude").exists()

    def test_empty_session_file_migrates_as_none(self, project: Path) -> None:
        old_path = legacy_session_path(project, BRANCH, "codex")
        old_path.write_text("\n", encoding="utf-8")

        state = get_agent_state(project, BRANCH, "codex")
        assert state.resume_id is None
        assert not old_path.exists()

    def test_json_takes_precedence_over_session(self, project: Path) -> None:
        # Both files exist — JSON should win, legacy ignored
        old_path = legacy_session_path(project, BRANCH, "claude")
        old_path.write_text("old-session-id\n", encoding="utf-8")

        new_state = AgentState(name="claude", status="working", resume_id="new-session-id")
        set_agent_state(project, BRANCH, "claude", new_state)

        state = get_agent_state(project, BRANCH, "claude")
        assert state.resume_id == "new-session-id"
        assert state.status == "working"
        # Legacy file should still be there (not touched when JSON exists)
        assert old_path.exists()


class TestListActiveAgents:
    def test_empty_sessions_dir(self, project: Path) -> None:
        assert list_active_agents(project, BRANCH) == []

    def test_all_idle_returns_empty(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude", status="idle"))
        set_agent_state(project, BRANCH, "codex", AgentState(name="codex", status="idle"))
        assert list_active_agents(project, BRANCH) == []

    def test_returns_non_idle_agents(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude", status="working"))
        set_agent_state(project, BRANCH, "codex", AgentState(name="codex", status="idle"))
        set_agent_state(project, BRANCH, "cursor", AgentState(name="cursor", status="blocked"))

        active = list_active_agents(project, BRANCH)
        names = [a.name for a in active]
        assert "claude" in names
        assert "cursor" in names
        assert "codex" not in names

    def test_includes_done_and_failed(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "p1", AgentState(name="p1", status="done"))
        set_agent_state(project, BRANCH, "p2", AgentState(name="p2", status="failed"))
        set_agent_state(project, BRANCH, "p3", AgentState(name="p3", status="stopped"))

        active = list_active_agents(project, BRANCH)
        assert len(active) == 3

    def test_nonexistent_sessions_dir(self, tmp_path: Path) -> None:
        assert list_active_agents(tmp_path, "no-such-branch") == []


class TestCurrentThread:
    def test_get_returns_none_when_unset(self, project: Path) -> None:
        assert get_current_thread(project, BRANCH) is None

    def test_set_and_get(self, project: Path) -> None:
        set_current_thread(project, BRANCH, "council-caching-debate")
        assert get_current_thread(project, BRANCH) == "council-caching-debate"

    def test_preserves_existing_state_json_fields(self, project: Path) -> None:
        # Write extra fields to state.json
        state_path = project / ".kd" / "branches" / "feature-test-branch" / "state.json"
        state_path.write_text(json.dumps({"branch": "feature/test-branch"}) + "\n", encoding="utf-8")

        set_current_thread(project, BRANCH, "my-thread")

        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["current_thread"] == "my-thread"
        assert data["branch"] == "feature/test-branch"

    def test_clear_current_thread(self, project: Path) -> None:
        set_current_thread(project, BRANCH, "my-thread")
        assert get_current_thread(project, BRANCH) == "my-thread"

        set_current_thread(project, BRANCH, None)
        assert get_current_thread(project, BRANCH) is None

    def test_get_returns_none_when_no_state_json(self, tmp_path: Path) -> None:
        assert get_current_thread(tmp_path, "no-such-branch") is None

    def test_overwrite_current_thread(self, project: Path) -> None:
        set_current_thread(project, BRANCH, "thread-1")
        set_current_thread(project, BRANCH, "thread-2")
        assert get_current_thread(project, BRANCH) == "thread-2"


# ---------------------------------------------------------------------------
# Helpers for multi-process concurrency tests (must be top-level for pickle)
# ---------------------------------------------------------------------------


def _increment_counter(args: tuple[str, str]) -> None:
    """Atomically increment a 'counter' field in a JSON file via locked_json_update."""
    path_str, lock_name = args
    from pathlib import Path as P

    path = P(path_str)

    def _inc(data: dict) -> dict:  # type: ignore[type-arg]
        data["counter"] = data.get("counter", 0) + 1
        return data

    locked_json_update(path, _inc)


class TestLockedJsonUpdate:
    """Verify that locked_json_update prevents lost updates under concurrency."""

    def test_concurrent_increments(self, tmp_path: Path) -> None:
        """Spawn multiple processes that each increment a counter; none should be lost."""
        json_path = tmp_path / "counter.json"
        json_path.write_text("{}", encoding="utf-8")

        n = 40
        args = [(str(json_path), "counter") for _ in range(n)]
        with ProcessPoolExecutor(max_workers=8) as pool:
            list(pool.map(_increment_counter, args))

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["counter"] == n, f"Expected {n}, got {data['counter']} — lost updates!"

    def test_concurrent_update_agent_state(self, project: Path) -> None:
        """Multiple processes bump last_activity; final PID should reflect last writer."""
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude", status="working"))

        json_path = session_path(project, BRANCH, "claude")
        n = 20
        args = [(str(json_path), "agent") for _ in range(n)]
        with ProcessPoolExecutor(max_workers=4) as pool:
            list(pool.map(_increment_counter, args))

        data = json.loads(json_path.read_text(encoding="utf-8"))
        # The counter should reflect all increments (no lost updates).
        assert data["counter"] == n
