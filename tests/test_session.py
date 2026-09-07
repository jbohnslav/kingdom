"""Tests for kingdom.session module."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from kingdom.session import (
    get_agent_state,
    get_current_thread,
    list_active_agents,
    session_path,
    set_current_thread,
    update_agent_state,
)
from kingdom.state import sessions_root

BRANCH = "feature/test-branch"


class TestPathHelpers:
    def test_session_path(self, project: Path) -> None:
        p = session_path(project, BRANCH, "claude")
        assert p == sessions_root(project, BRANCH) / "claude.json"


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
                    "ticket": "042",
                    "thread": "042-work",
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
        assert state.ticket == "042"
        assert state.thread == "042-work"
        assert state.started_at == "2026-02-07T15:30:00Z"
        assert state.last_activity == "2026-02-07T15:44:00Z"


class TestUpdateAgentState:
    def test_updates_single_field(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude", status="idle", resume_id="sess-1")

        updated = update_agent_state(project, BRANCH, "claude", status="working")
        assert updated.status == "working"
        assert updated.resume_id == "sess-1"  # preserved

        # Verify persisted
        reread = get_agent_state(project, BRANCH, "claude")
        assert reread.status == "working"
        assert reread.resume_id == "sess-1"

    def test_updates_multiple_fields(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude")

        updated = update_agent_state(
            project,
            BRANCH,
            "claude",
            status="working",
            pid=9999,
            ticket="042",
        )
        assert updated.status == "working"
        assert updated.pid == 9999
        assert updated.ticket == "042"

    def test_unknown_field_raises(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude")

        with pytest.raises(ValueError, match="Unknown AgentState field"):
            update_agent_state(project, BRANCH, "claude", bogus="value")


class TestListActiveAgents:
    def test_empty_sessions_dir(self, project: Path) -> None:
        assert list_active_agents(project, BRANCH) == []

    def test_all_idle_returns_empty(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude", status="idle")
        update_agent_state(project, BRANCH, "codex", status="idle")
        assert list_active_agents(project, BRANCH) == []

    def test_returns_non_idle_agents(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude", status="working")
        update_agent_state(project, BRANCH, "codex", status="idle")
        update_agent_state(project, BRANCH, "extra", status="blocked")

        active = list_active_agents(project, BRANCH)
        names = [a.name for a in active]
        assert "claude" in names
        assert "extra" in names
        assert "codex" not in names

    def test_includes_done_and_failed(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "p1", status="done")
        update_agent_state(project, BRANCH, "p2", status="failed")
        update_agent_state(project, BRANCH, "p3", status="stopped")

        active = list_active_agents(project, BRANCH)
        assert len(active) == 3

    def test_nonexistent_sessions_dir(self, tmp_path: Path) -> None:
        assert list_active_agents(tmp_path, "no-such-branch") == []


class TestNewSessionFields:
    """Tests for start_sha, review_bounce_count, and new statuses."""

    def test_new_statuses_in_agent_statuses(self) -> None:
        from kingdom.session import AGENT_STATUSES

        assert "awaiting_council" in AGENT_STATUSES
        assert "needs_king_review" in AGENT_STATUSES

    def test_start_sha_defaults_to_none(self, project: Path) -> None:
        state = get_agent_state(project, BRANCH, "claude")
        assert state.start_sha is None

    def test_review_bounce_count_defaults_to_zero(self, project: Path) -> None:
        state = get_agent_state(project, BRANCH, "claude")
        assert state.review_bounce_count == 0

    def test_start_sha_persists(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude", status="working", start_sha="abc123def")
        state = get_agent_state(project, BRANCH, "claude")
        assert state.start_sha == "abc123def"

    def test_review_bounce_count_persists(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude", status="working", review_bounce_count=2)
        state = get_agent_state(project, BRANCH, "claude")
        assert state.review_bounce_count == 2

    def test_update_start_sha(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude")
        updated = update_agent_state(project, BRANCH, "claude", start_sha="deadbeef")
        assert updated.start_sha == "deadbeef"
        reread = get_agent_state(project, BRANCH, "claude")
        assert reread.start_sha == "deadbeef"

    def test_update_review_bounce_count(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "claude")
        updated = update_agent_state(project, BRANCH, "claude", review_bounce_count=3)
        assert updated.review_bounce_count == 3
        reread = get_agent_state(project, BRANCH, "claude")
        assert reread.review_bounce_count == 3

    def test_backward_compat_old_session_without_new_fields(self, project: Path) -> None:
        """Old session files without start_sha/review_bounce_count load with safe defaults."""
        p = session_path(project, BRANCH, "claude")
        p.write_text(
            json.dumps({"name": "claude", "status": "working", "pid": 1234}) + "\n",
            encoding="utf-8",
        )
        state = get_agent_state(project, BRANCH, "claude")
        assert state.start_sha is None
        assert state.review_bounce_count == 0
        assert state.status == "working"
        assert state.pid == 1234

    def test_new_statuses_work_with_list_active(self, project: Path) -> None:
        update_agent_state(project, BRANCH, "p1", status="awaiting_council")
        update_agent_state(project, BRANCH, "p2", status="needs_king_review")
        active = list_active_agents(project, BRANCH)
        statuses = {a.name: a.status for a in active}
        assert statuses["p1"] == "awaiting_council"
        assert statuses["p2"] == "needs_king_review"


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
# Concurrency tests using subprocesses
# ---------------------------------------------------------------------------

# Inline script executed by each worker subprocess.  It adds the *worktree*
# src/ to sys.path so the correct ``kingdom.state`` is imported even when
# pytest is invoked from the main repository root.
WORKER_SCRIPT = textwrap.dedent("""\
    import json, sys, pathlib
    sys.path.insert(0, sys.argv[1])       # src/ directory
    from kingdom.state import locked_json_update
    path = pathlib.Path(sys.argv[2])
    def inc(data):
        data["counter"] = data.get("counter", 0) + 1
        return data
    locked_json_update(path, inc)
""")


def spawn_workers(src_dir: str, json_path: str, n: int) -> None:
    """Launch *n* subprocesses that each atomically increment a counter."""
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", WORKER_SCRIPT, src_dir, json_path],
        )
        for _ in range(n)
    ]
    for p in procs:
        p.wait()
        assert p.returncode == 0, f"Worker exited with {p.returncode}"


class TestLockedJsonUpdate:
    """Verify that locked_json_update prevents lost updates under concurrency."""

    @staticmethod
    def src_dir() -> str:
        """Return the src/ directory for this worktree."""
        return str(Path(__file__).resolve().parent.parent / "src")

    def test_concurrent_increments(self, tmp_path: Path) -> None:
        """Spawn multiple processes that each increment a counter; none should be lost."""
        json_path = tmp_path / "counter.json"
        json_path.write_text("{}", encoding="utf-8")

        n = 40
        spawn_workers(self.src_dir(), str(json_path), n)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["counter"] == n, f"Expected {n}, got {data['counter']} — lost updates!"

    def test_concurrent_update_agent_state(self, project: Path) -> None:
        """Multiple processes bump a counter on an existing agent state file."""
        update_agent_state(project, BRANCH, "claude", status="working")

        json_path = session_path(project, BRANCH, "claude")
        n = 20
        spawn_workers(self.src_dir(), str(json_path), n)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        # The counter should reflect all increments (no lost updates).
        assert data["counter"] == n
