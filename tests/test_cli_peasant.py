"""Tests for the peasant CLI commands."""

from __future__ import annotations

import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kingdom.cli.peasant import peasant_app, resolve_invocation_git_root, resolve_peasant_context
from kingdom.cli.ticket import ticket_app
from kingdom.session import AgentState, get_agent_state, set_agent_state, update_agent_state
from kingdom.state import backlog_root, ensure_branch_layout, logs_root, normalize_branch_name, set_current_run
from kingdom.thread import add_message, create_thread, list_messages, thread_dir
from kingdom.ticket import Ticket, find_ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/peasant-test"


def setup_project(base: Path) -> None:
    """Create a minimal project with branch layout and a test ticket."""
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


def create_test_ticket(base: Path, ticket_id: str = "kin-test", status: str = "open") -> Path:
    """Create a test ticket and return its path."""
    tickets_dir = base / ".kd" / "branches" / "feature-peasant-test" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket = Ticket(
        id=ticket_id,
        status=status,
        title="Test ticket",
        body="Do the thing.\n\n## Acceptance\n\n- [ ] It works",
        created=datetime.now(UTC),
    )
    path = tickets_dir / f"{ticket_id}.md"
    write_ticket(ticket, path)
    return path


class TestPeasantStart:
    def test_start_creates_session_and_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Mock Popen so we don't actually launch a process
            mock_proc = MagicMock()
            mock_proc.pid = 12345

            # Mock worktree creation
            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[]),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Started peasant-kin-test" in result.output
            assert "pid 12345" in result.output

            # Session should be created
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "working"
            assert state.pid == 12345
            assert state.ticket == "kin-test"
            assert state.thread == "kin-test-work"

            # Thread should be created
            tdir = thread_dir(base, BRANCH, "kin-test-work")
            assert tdir.exists()

    def test_start_hand_mode(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Mock Popen so we don't actually launch a process
            mock_proc = MagicMock()
            mock_proc.pid = 12345

            # Mock worktree creation - ensure it is NOT called
            with (
                patch("kingdom.cli.peasant.create_worktree") as mock_create_worktree,
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand"])

            assert result.exit_code == 0, result.output
            assert "Running in hand mode" in result.output
            assert "pid 12345" in result.output

            # create_worktree should NOT be called
            mock_create_worktree.assert_not_called()

            # Session should be created
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "working"
            assert state.pid == 12345

    def test_start_hand_mode_preserves_agent_when_dead_sessions_exist(self) -> None:
        """The --hand loop variable must not shadow the `agent` parameter."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Create a dead peasant session so the guard loop iterates
            set_agent_state(
                base,
                BRANCH,
                "peasant-other",
                AgentState(name="peasant-other", status="working", pid=99999999),
            )

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand", "--agent", "claude"])

            assert result.exit_code == 0, result.output

            # The agent_backend should be the string "claude", not an AgentState object
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.agent_backend == "claude", f"Expected 'claude', got {state.agent_backend!r}"

    def test_start_refuses_if_already_running(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Set up a "running" session with a live PID
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="working", pid=os.getpid()),
            )

            result = runner.invoke(peasant_app, ["start", "kin-test"])

            assert result.exit_code == 1
            assert "already running" in result.output

    def test_start_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["start", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_start_blocks_on_in_review_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = base / ".kd" / "branches" / "feature-peasant-test" / "tickets"
            tickets_dir.mkdir(parents=True, exist_ok=True)
            ticket = Ticket(
                id="kin-rev1",
                status="in_review",
                title="Review ticket",
                body="Under review",
                created=datetime.now(UTC),
            )
            path = tickets_dir / "kin-rev1.md"
            write_ticket(ticket, path)

            result = runner.invoke(peasant_app, ["start", "kin-rev1"])

            assert result.exit_code == 1
            assert "in_review" in result.output

    def test_start_transitions_open_to_in_progress(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            ticket_path = create_test_ticket(base)  # creates with status="open"

            with patch("kingdom.cli.launch_work_background", return_value=12345):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand"])

            assert result.exit_code == 0, result.output
            # Verify the ticket was transitioned to in_progress
            ticket = read_ticket(ticket_path)
            assert ticket.status == "in_progress"

    def test_start_with_watch_calls_peasant_watch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.peasant_watch") as mock_watch,
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[]),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--watch"])

            assert result.exit_code == 0, result.output
            assert "Started peasant-kin-test" in result.output
            mock_watch.assert_called_once_with("kin-test")

    def test_start_without_watch_does_not_call_peasant_watch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.peasant_watch") as mock_watch,
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[]),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test"])

            assert result.exit_code == 0, result.output
            mock_watch.assert_not_called()

    def test_start_hand_with_watch_calls_peasant_watch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.peasant_watch") as mock_watch,
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand", "-w"])

            assert result.exit_code == 0, result.output
            assert "Running in hand mode" in result.output
            mock_watch.assert_called_once_with("kin-test")

    def test_start_hand_mode_seeds_state_before_launch(self) -> None:
        """Worker must see hand_mode=True on first read (race fix for 4658)."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            observed_state_during_launch: list[AgentState] = []

            def spy_launch(*args: object, **kwargs: object) -> int:
                # Simulate the worker reading session state immediately on launch
                state = get_agent_state(base, BRANCH, "peasant-kin-test")
                observed_state_during_launch.append(state)
                return 42  # fake pid

            with patch("kingdom.cli.launch_work_background", side_effect=spy_launch):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand"])

            assert result.exit_code == 0, result.output
            assert len(observed_state_during_launch) == 1
            state = observed_state_during_launch[0]
            assert state.hand_mode is True
            assert state.status == "working"
            assert state.ticket == "kin-test"
            assert state.agent_backend is not None

    def test_start_fast_worker_failure_not_clobbered(self) -> None:
        """If worker writes status=failed before parent records pid, status stays failed."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            def failing_launch(*args: object, **kwargs: object) -> int:
                # Simulate a worker that fails immediately and writes failed status
                update_agent_state(base, BRANCH, "peasant-kin-test", status="failed")
                return 99

            with patch("kingdom.cli.launch_work_background", side_effect=failing_launch):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand"])

            assert result.exit_code == 0, result.output
            # The parent's post-launch update should only set pid, not clobber status
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "failed"
            assert state.pid == 99

    def test_start_launch_exception_sets_failed(self) -> None:
        """If launch itself throws, session should be marked failed, not stuck working."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch(
                "kingdom.cli.launch_work_background",
                side_effect=RuntimeError("tmux not found"),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand"])

            assert result.exit_code == 1
            assert "Failed to launch" in result.output
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "failed"

    def test_start_clears_resume_id_when_agent_changes(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(
                    name="peasant-kin-test",
                    status="failed",
                    resume_id="claude-session",
                    agent_backend="claude",
                ),
            )

            observed_state_during_launch: list[AgentState] = []

            def spy_launch(*args: object, **kwargs: object) -> int:
                state = get_agent_state(base, BRANCH, "peasant-kin-test")
                observed_state_during_launch.append(state)
                return 42

            with patch("kingdom.cli.launch_work_background", side_effect=spy_launch):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand", "--agent", "codex"])

            assert result.exit_code == 0, result.output
            assert len(observed_state_during_launch) == 1
            state = observed_state_during_launch[0]
            assert state.agent_backend == "codex"
            assert state.resume_id is None

    def test_start_preserves_resume_id_when_agent_matches(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(
                    name="peasant-kin-test",
                    status="failed",
                    resume_id="codex-session",
                    agent_backend="codex",
                ),
            )

            observed_state_during_launch: list[AgentState] = []

            def spy_launch(*args: object, **kwargs: object) -> int:
                state = get_agent_state(base, BRANCH, "peasant-kin-test")
                observed_state_during_launch.append(state)
                return 42

            with patch("kingdom.cli.launch_work_background", side_effect=spy_launch):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand", "--agent", "codex"])

            assert result.exit_code == 0, result.output
            assert len(observed_state_during_launch) == 1
            state = observed_state_during_launch[0]
            assert state.agent_backend == "codex"
            assert state.resume_id == "codex-session"

    def test_start_warns_on_uncommitted_changes(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[" M dirty.py"]),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "uncommitted" in result.output.lower()
            assert "--hand" in result.output

    def test_start_ignores_kd_only_uncommitted_changes(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[]) as mock_check,
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "uncommitted" not in result.output.lower()
            mock_check.assert_called_once_with(base, ignore_kd=True)

    def test_start_no_preflight_suppresses_warning(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes") as mock_check,
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--no-preflight"])

            assert result.exit_code == 0, result.output
            mock_check.assert_not_called()

    def test_start_hand_mode_skips_preflight(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes") as mock_check,
            ):
                result = runner.invoke(peasant_app, ["start", "kin-test", "--hand"])

            assert result.exit_code == 0, result.output
            mock_check.assert_not_called()


class TestPeasantStatus:
    def test_status_no_peasants(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["status"])

            assert result.exit_code == 0
            assert "No active peasants" in result.output

    def test_status_shows_active_peasants(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            now = datetime.now(UTC).isoformat()
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-042",
                AgentState(
                    name="peasant-kin-042",
                    status="working",
                    pid=99999,
                    ticket="kin-042",
                    agent_backend="claude",
                    started_at=now,
                    last_activity=now,
                ),
            )

            with patch("os.kill"):  # Mock kill so liveness check doesn't mark as dead
                result = runner.invoke(peasant_app, ["status"])

            assert result.exit_code == 0
            assert "kin-042" in result.output
            assert "working" in result.output
            assert "claude" in result.output

    def test_terminal_elapsed_freezes_at_last_activity(self) -> None:
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            for status in ("done", "failed", "stopped"):
                set_agent_state(
                    base,
                    BRANCH,
                    f"peasant-kin-{status}",
                    AgentState(
                        name=f"peasant-kin-{status}",
                        status=status,
                        ticket=f"kin-{status}",
                        started_at="2026-08-03T12:00:00+00:00",
                        last_activity="2026-08-03T12:30:00+00:00",
                    ),
                )

            with patch("kingdom.cli.peasant.datetime") as clock:
                clock.now.return_value = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
                result = runner.invoke(peasant_app, ["status", "--all", "--json"])

            assert result.exit_code == 0, result.output
            rows = json.loads(result.output)
            assert {row["status"]: row["elapsed_minutes"] for row in rows} == {
                "done": 30,
                "failed": 30,
                "stopped": 30,
            }

    def test_active_elapsed_continues_using_current_time(self) -> None:
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-active",
                AgentState(
                    name="peasant-kin-active",
                    status="working",
                    pid=99999,
                    ticket="kin-active",
                    started_at="2026-08-03T12:00:00+00:00",
                    last_activity="2026-08-03T12:30:00+00:00",
                ),
            )

            with (
                patch("kingdom.cli.peasant.datetime") as clock,
                patch("os.kill"),
            ):
                clock.now.return_value = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
                result = runner.invoke(peasant_app, ["status", "--json"])

            assert result.exit_code == 0, result.output
            rows = json.loads(result.output)
            assert rows[0]["elapsed_minutes"] == 120

    def test_failed_status_exposes_infrastructure_failure_kind(self) -> None:
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-auth",
                AgentState(
                    name="peasant-kin-auth",
                    status="failed",
                    failure_kind="authentication",
                    ticket="kin-auth",
                ),
            )

            json_result = runner.invoke(peasant_app, ["status", "--all", "--json"])
            human_result = runner.invoke(peasant_app, ["status", "--all"])

            assert json_result.exit_code == 0, json_result.output
            assert json.loads(json_result.output)[0]["failure_kind"] == "authentication"
            assert human_result.exit_code == 0, human_result.output
            assert "failed/authentication" in human_result.output

    def test_status_ignores_non_peasant_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # A regular agent session (not a peasant)
            set_agent_state(
                base,
                BRANCH,
                "claude",
                AgentState(name="claude", status="working"),
            )

            result = runner.invoke(peasant_app, ["status"])

            assert result.exit_code == 0
            assert "No active peasants" in result.output


class TestPeasantShow:
    def test_show_worklog(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            ticket_path = create_test_ticket(base)

            # Add a worklog section to the ticket
            content = ticket_path.read_text(encoding="utf-8")
            content += "\n\n## Worklog\n\n- [09:00] Started work\n- [09:30] Fixed the bug\n"
            ticket_path.write_text(content, encoding="utf-8")

            # Create the logs dir so agent-live.log section doesn't error
            peasant_logs_dir = logs_root(base, BRANCH) / "peasant-kin-test"
            peasant_logs_dir.mkdir(parents=True, exist_ok=True)

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "Started work" in result.output
            assert "Fixed the bug" in result.output

    def test_show_no_worklog(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "no worklog entries" in result.output

    def test_show_agent_activity(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Create agent-live.log with some plain-text content
            peasant_logs_dir = logs_root(base, BRANCH) / "peasant-kin-test"
            peasant_logs_dir.mkdir(parents=True, exist_ok=True)
            (peasant_logs_dir / "agent-live.log").write_text(
                "Reading the source file for context\nApplying the fix to main.py\n",
                encoding="utf-8",
            )

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "Agent Activity" in result.output
            assert "Reading the source file for context" in result.output

    def test_show_no_agent_log(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "no agent activity log" in result.output

    def test_show_commits(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()

            # Set up a real git repo so git log works
            import subprocess

            subprocess.run(["git", "init", "-b", "main"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(base), capture_output=True)

            setup_project(base)
            create_test_ticket(base)

            # Initial commit on main
            subprocess.run(["git", "add", "."], cwd=str(base), capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=str(base), capture_output=True)

            # Create the feature branch (used as base for commit range)
            subprocess.run(["git", "checkout", "-b", BRANCH], cwd=str(base), capture_output=True)

            # Create peasant branch with a commit
            subprocess.run(["git", "checkout", "-b", "ticket/kin-test"], cwd=str(base), capture_output=True)
            (base / "fix.py").write_text("# fix\n", encoding="utf-8")
            subprocess.run(["git", "add", "fix.py"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "commit", "-m", "fix: the bug"], cwd=str(base), capture_output=True)

            # Switch back to main so HEAD != ticket branch
            subprocess.run(["git", "checkout", "main"], cwd=str(base), capture_output=True)

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "Commits" in result.output
            assert "fix: the bug" in result.output

    def test_show_commits_excludes_parent_only_commits(self) -> None:
        """Verify two-dot range: commits only on parent branch are excluded."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            import subprocess

            subprocess.run(["git", "init", "-b", "main"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(base), capture_output=True)

            setup_project(base)
            create_test_ticket(base)

            # Initial commit on main
            subprocess.run(["git", "add", "."], cwd=str(base), capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=str(base), capture_output=True)

            # Create the feature branch (used as base for commit range)
            subprocess.run(["git", "checkout", "-b", BRANCH], cwd=str(base), capture_output=True)

            # Create peasant branch with a commit
            subprocess.run(["git", "checkout", "-b", "ticket/kin-test"], cwd=str(base), capture_output=True)
            (base / "fix.py").write_text("# fix\n", encoding="utf-8")
            subprocess.run(["git", "add", "fix.py"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "commit", "-m", "fix: peasant work"], cwd=str(base), capture_output=True)

            # Switch to feature branch and add a commit not on the ticket branch
            subprocess.run(["git", "checkout", BRANCH], cwd=str(base), capture_output=True)
            (base / "unrelated.py").write_text("# unrelated\n", encoding="utf-8")
            subprocess.run(["git", "add", "unrelated.py"], cwd=str(base), capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "feat: unrelated parent work"],
                cwd=str(base),
                capture_output=True,
            )

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "fix: peasant work" in result.output
            assert "unrelated parent work" not in result.output

    def test_show_commits_with_normalized_current_run(self) -> None:
        """Regression: kd start stores normalized name in .kd/current.

        When the branch has slashes (e.g. feature/peasant-test), kd start
        writes the normalized form (feature-peasant-test) to .kd/current.
        peasant show must resolve back to the real git ref for git log.
        """
        with runner.isolated_filesystem():
            base = Path.cwd()
            import subprocess

            subprocess.run(["git", "init", "-b", "main"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(base), capture_output=True)

            # Mimic real kd start: ensure_branch_layout + set_current_run with NORMALIZED name
            ensure_branch_layout(base, BRANCH)
            normalized = normalize_branch_name(BRANCH)
            set_current_run(base, normalized)

            # Store original branch name in state.json (like kd start does)
            from kingdom.state import branch_root, read_json, write_json

            state_path = branch_root(base, BRANCH) / "state.json"
            state_data = read_json(state_path)
            state_data["branch"] = BRANCH
            write_json(state_path, state_data)

            create_test_ticket(base)

            # Initial commit on main
            subprocess.run(["git", "add", "."], cwd=str(base), capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=str(base), capture_output=True)

            # Create the feature branch with slashes (the real git ref)
            subprocess.run(["git", "checkout", "-b", BRANCH], cwd=str(base), capture_output=True)

            # Create peasant branch with a commit
            subprocess.run(["git", "checkout", "-b", "ticket/kin-test"], cwd=str(base), capture_output=True)
            (base / "fix.py").write_text("# fix\n", encoding="utf-8")
            subprocess.run(["git", "add", "fix.py"], cwd=str(base), capture_output=True)
            subprocess.run(["git", "commit", "-m", "fix: slash branch bug"], cwd=str(base), capture_output=True)

            # Switch back to main so HEAD != ticket branch
            subprocess.run(["git", "checkout", "main"], cwd=str(base), capture_output=True)

            result = runner.invoke(peasant_app, ["show", "kin-test"])

            assert result.exit_code == 0
            assert "Commits" in result.output
            assert "fix: slash branch bug" in result.output

    def test_show_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["show", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantStop:
    def test_stop_kills_process_group(self) -> None:
        """Stop sends SIGTERM to the entire process group, not just the harness PID."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="working", pid=99999),
            )

            # killpg SIGTERM succeeds, then killpg(0) raises OSError (all dead)
            with patch("os.killpg") as mock_killpg:
                mock_killpg.side_effect = [None, OSError("No such process")]
                result = runner.invoke(peasant_app, ["stop", "kin-test"])

            assert result.exit_code == 0
            assert "SIGTERM" in result.output
            assert "process group" in result.output
            mock_killpg.assert_any_call(99999, signal.SIGTERM)

            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "stopped"

    def test_stop_sigkill_fallback(self) -> None:
        """If processes survive SIGTERM, SIGKILL is sent after timeout."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="working", pid=99999),
            )

            # Simulate: SIGTERM succeeds, processes stay alive, then finally die after SIGKILL
            call_count = 0

            def killpg_side_effect(pgid: int, sig: int) -> None:
                nonlocal call_count
                call_count += 1
                if sig == signal.SIGTERM:
                    return  # SIGTERM sent OK
                if sig == 0:
                    return  # process still alive (probe succeeds)
                if sig == signal.SIGKILL:
                    return  # SIGKILL sent OK

            with (
                patch("os.killpg", side_effect=killpg_side_effect),
                patch("time.monotonic") as mock_mono,
                patch("time.sleep"),
            ):
                # First call: before deadline check; second: past deadline
                mock_mono.side_effect = [0, 0, 6]
                result = runner.invoke(peasant_app, ["stop", "kin-test"])

            assert result.exit_code == 0
            assert "SIGKILL" in result.output

            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "stopped"

    def test_stop_process_group_already_dead(self) -> None:
        """If the process group is already dead, stop still updates session status."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="working", pid=99999),
            )

            with patch("os.killpg", side_effect=OSError("No such process")):
                result = runner.invoke(peasant_app, ["stop", "kin-test"])

            assert result.exit_code == 0
            assert "not found" in result.output.lower() or "No such process" in result.output
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "stopped"

    def test_stop_not_running(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="done"),
            )

            result = runner.invoke(peasant_app, ["stop", "kin-test"])

            assert result.exit_code == 1
            assert "not running" in result.output

    def test_stop_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["stop", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_stop_no_pid_fails_without_force(self) -> None:
        """Stop without --force should fail when no PID is tracked."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="working", pid=None),
            )

            result = runner.invoke(peasant_app, ["stop", "kin-test"])

            assert result.exit_code == 1
            assert "No PID" in result.output
            assert "--force" in result.output

    def test_stop_force_closes_without_pid(self) -> None:
        """Stop --force should close session state even when no PID is tracked."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(name="peasant-kin-test", status="working", pid=None),
            )

            result = runner.invoke(peasant_app, ["stop", "kin-test", "--force"])

            assert result.exit_code == 0
            assert "force-closing" in result.output
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "stopped"

    def test_kill_peasant_process_rejects_pid_zero(self) -> None:
        """kill_peasant_process must not call killpg with pid=0 (would signal caller)."""
        from kingdom.cli.peasant import kill_peasant_process

        with patch("os.killpg") as mock_killpg:
            result = kill_peasant_process(0, "test")

        assert result is False
        mock_killpg.assert_not_called()


class TestPeasantPrune:
    def test_prune_marks_stale_sessions_stopped(self) -> None:
        """Prune should mark working sessions with no PID as stopped."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-stale1",
                AgentState(name="peasant-stale1", status="working", pid=None),
            )
            set_agent_state(
                base,
                BRANCH,
                "peasant-healthy",
                AgentState(name="peasant-healthy", status="done"),
            )

            result = runner.invoke(peasant_app, ["prune"])

            assert result.exit_code == 0
            assert "Pruned" in result.output
            assert "peasant-stale1" in result.output
            assert "1 session(s) pruned" in result.output
            state = get_agent_state(base, BRANCH, "peasant-stale1")
            assert state.status == "stopped"

    def test_prune_dry_run(self) -> None:
        """Prune --dry-run should show what would be pruned without changing state."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-stale1",
                AgentState(name="peasant-stale1", status="working", pid=None),
            )

            result = runner.invoke(peasant_app, ["prune", "--dry-run"])

            assert result.exit_code == 0
            assert "Would prune" in result.output
            # State should NOT be changed
            state = get_agent_state(base, BRANCH, "peasant-stale1")
            assert state.status == "working"

    def test_prune_nothing_stale(self) -> None:
        """Prune with no stale sessions should report nothing to do."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["prune"])

            assert result.exit_code == 0
            assert "No stale" in result.output


class TestPeasantClean:
    def test_clean_removes_worktree(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch("kingdom.cli.peasant.remove_worktree") as mock_remove:
                result = runner.invoke(peasant_app, ["clean", "--force", "kin-test"])

            assert result.exit_code == 0
            assert "worktree removed" in result.output
            mock_remove.assert_called_once_with(
                base,
                "kin-test",
                git_root=base,
                feature=BRANCH,
            )

    def test_clean_confirms_before_removing(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch("kingdom.cli.peasant.remove_worktree") as mock_remove:
                result = runner.invoke(peasant_app, ["clean", "kin-test"], input="y\n")

            assert result.exit_code == 0
            assert "Remove worktree for kin-test?" in result.output
            mock_remove.assert_called_once()

    def test_clean_aborts_on_no(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch("kingdom.cli.peasant.remove_worktree") as mock_remove:
                result = runner.invoke(peasant_app, ["clean", "kin-test"], input="n\n")

            assert result.exit_code != 0
            mock_remove.assert_not_called()

    def test_clean_no_worktree(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch("kingdom.cli.peasant.remove_worktree", side_effect=FileNotFoundError("No worktree")):
                result = runner.invoke(peasant_app, ["clean", "--force", "kin-test"])

            assert result.exit_code == 1
            assert "No worktree" in result.output


class TestPeasantSync:
    def test_sync_merges_parent_branch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Create fake worktree directory
            from kingdom.state import state_root

            worktree_path = state_root(base) / "worktrees" / "kin-test"
            worktree_path.mkdir(parents=True, exist_ok=True)

            merge_result = MagicMock()
            merge_result.returncode = 0
            merge_result.stdout = "Already up to date."
            merge_result.stderr = ""

            with patch("subprocess.run", return_value=merge_result):
                result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "[1/2]" in result.output
            assert "[2/2]" in result.output
            assert "Already up to date" in result.output
            assert "sync complete" in result.output

    def test_sync_refuses_while_running(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="working", pid=os.getpid()),
            )

            result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 1
            assert "running" in result.output.lower()
            assert "stop" in result.output.lower()

    def test_sync_allows_when_dead_pid(self) -> None:
        """Status=working but PID is dead — should allow sync."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="working", pid=99999999),
            )

            from kingdom.state import state_root

            worktree_path = state_root(base) / "worktrees" / "kin-test"
            worktree_path.mkdir(parents=True, exist_ok=True)

            merge_result = MagicMock()
            merge_result.returncode = 0
            merge_result.stdout = "Already up to date."
            merge_result.stderr = ""

            with patch("subprocess.run", return_value=merge_result):
                result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "sync complete" in result.output

    def test_sync_no_worktree(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 1
            assert "No worktree" in result.output

    def test_sync_merge_conflict_aborts(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            from kingdom.state import state_root

            worktree_path = state_root(base) / "worktrees" / "kin-test"
            worktree_path.mkdir(parents=True, exist_ok=True)

            merge_result = MagicMock()
            merge_result.returncode = 1
            merge_result.stdout = "CONFLICT (content): Merge conflict in foo.py"
            merge_result.stderr = ""

            abort_result = MagicMock()
            abort_result.returncode = 0

            with patch("subprocess.run", side_effect=[merge_result, abort_result]) as mock_run:
                result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 1
            assert "Merge failed" in result.output
            assert "resolve manually" in result.output.lower()

            # Should have called git merge --abort
            calls = mock_run.call_args_list
            assert any("--abort" in str(c) for c in calls)

    def test_sync_runs_init_script(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            from kingdom.state import state_root

            worktree_path = state_root(base) / "worktrees" / "kin-test"
            worktree_path.mkdir(parents=True, exist_ok=True)

            # Create executable init script
            init_script = state_root(base) / "init-worktree.sh"
            init_script.write_text("#!/bin/bash\necho 'init ran'", encoding="utf-8")
            init_script.chmod(0o755)

            merge_result = MagicMock()
            merge_result.returncode = 0
            merge_result.stdout = "Already up to date."
            merge_result.stderr = ""

            init_run_result = MagicMock()
            init_run_result.returncode = 0
            init_run_result.stdout = "init ran"
            init_run_result.stderr = ""

            with patch("subprocess.run", side_effect=[merge_result, init_run_result]):
                result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "init-worktree.sh" in result.output
            assert "sync complete" in result.output

    def test_sync_non_executable_init_script(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            from kingdom.state import state_root

            worktree_path = state_root(base) / "worktrees" / "kin-test"
            worktree_path.mkdir(parents=True, exist_ok=True)

            # Create init script but do NOT make it executable
            init_script = state_root(base) / "init-worktree.sh"
            init_script.write_text("#!/bin/bash\necho 'init ran'", encoding="utf-8")
            init_script.chmod(0o644)

            merge_result = MagicMock()
            merge_result.returncode = 0
            merge_result.stdout = "Already up to date."
            merge_result.stderr = ""

            with patch("subprocess.run", return_value=merge_result):
                result = runner.invoke(peasant_app, ["sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "not executable" in result.output

    def test_sync_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["sync", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


def setup_work_thread(base: Path, ticket_id: str = "kin-test") -> str:
    """Create a work thread for a ticket. Returns thread_id."""
    thread_id = f"{ticket_id}-work"
    session_name = f"peasant-{ticket_id}"
    create_thread(base, BRANCH, thread_id, [session_name, "king"], "work")
    return thread_id


class TestPeasantMsg:
    def test_msg_sends_directive(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            thread_id = setup_work_thread(base)

            result = runner.invoke(peasant_app, ["msg", "kin-test", "focus on tests"])

            assert result.exit_code == 0, result.output
            assert "directive sent" in result.output

            # Message should appear in the thread
            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 1
            assert messages[0].from_ == "king"
            assert messages[0].to == "peasant-kin-test"
            assert "focus on tests" in messages[0].body

    def test_msg_multiple_directives(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            thread_id = setup_work_thread(base)

            runner.invoke(peasant_app, ["msg", "kin-test", "first directive"])
            runner.invoke(peasant_app, ["msg", "kin-test", "second directive"])

            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 2
            assert "first directive" in messages[0].body
            assert "second directive" in messages[1].body

    def test_msg_no_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            # Don't create the work thread

            result = runner.invoke(peasant_app, ["msg", "kin-test", "hello"])

            assert result.exit_code == 1
            assert "No work thread" in result.output

    def test_msg_warns_dead_peasant(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            thread_id = setup_work_thread(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="done"),
            )

            result = runner.invoke(peasant_app, ["msg", "kin-test", "do something"])

            assert result.exit_code == 0, result.output
            assert "directive sent" in result.output
            assert "Warning" in result.output
            assert "not running" in result.output

            # Message should still be written to thread
            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 1
            assert "do something" in messages[0].body

    def test_msg_no_warning_when_alive(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            setup_work_thread(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="working", pid=os.getpid()),
            )

            result = runner.invoke(peasant_app, ["msg", "kin-test", "keep going"])

            assert result.exit_code == 0, result.output
            assert "directive sent" in result.output
            assert "Warning" not in result.output

    def test_msg_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["msg", "kin-nope", "hello"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantRead:
    def test_read_shows_peasant_messages(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            thread_id = setup_work_thread(base)

            # Add some messages — one from king, two from peasant
            add_message(base, BRANCH, thread_id, from_="king", to="peasant-kin-test", body="Start working")
            add_message(base, BRANCH, thread_id, from_="peasant-kin-test", to="king", body="Working on it")
            add_message(base, BRANCH, thread_id, from_="peasant-kin-test", to="king", body="STATUS: BLOCKED\nNeed help")

            result = runner.invoke(peasant_app, ["read", "kin-test"])

            assert result.exit_code == 0
            assert "Working on it" in result.output
            assert "BLOCKED" in result.output
            # King's message should not appear (filtered to peasant only)
            assert "Start working" not in result.output

    def test_read_no_messages(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            setup_work_thread(base)

            result = runner.invoke(peasant_app, ["read", "kin-test"])

            assert result.exit_code == 0
            assert "No messages" in result.output

    def test_read_last_n(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            thread_id = setup_work_thread(base)

            # Add several peasant messages
            for i in range(5):
                add_message(base, BRANCH, thread_id, from_="peasant-kin-test", to="king", body=f"Message {i}")

            result = runner.invoke(peasant_app, ["read", "kin-test", "--last", "2"])

            assert result.exit_code == 0
            assert "Message 3" in result.output
            assert "Message 4" in result.output
            assert "Message 0" not in result.output

    def test_read_last_zero_rejected(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            setup_work_thread(base)

            result = runner.invoke(peasant_app, ["read", "kin-test", "--last", "0"])

            assert result.exit_code != 0

    def test_read_last_negative_rejected(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            setup_work_thread(base)

            result = runner.invoke(peasant_app, ["read", "kin-test", "--last", "-1"])

            assert result.exit_code != 0

    def test_read_no_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(peasant_app, ["read", "kin-test"])

            assert result.exit_code == 1
            assert "No work thread" in result.output

    def test_read_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["read", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantReview:
    def test_review_shows_results(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            ticket_path = create_test_ticket(base, status="in_review")

            # Add a worklog to the ticket
            from kingdom.harness import append_worklog

            append_worklog(ticket_path, "Did some work")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            with patch("subprocess.run") as mock_run:
                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = " src/foo.py | 5 ++-\n 1 file changed"
                diff_result.stderr = ""

                mock_run.return_value = diff_result

                result = runner.invoke(peasant_app, ["review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Did some work" in result.output
            assert "needs_king_review" in result.output
            assert "kd peasant accept" in result.output

    def test_review_accept_closes_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    # Branch not yet merged
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    # Clean working tree
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                else:
                    # git merge
                    result.returncode = 0
                    result.stdout = "Already up to date."
                    result.stderr = ""
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "accepted" in result.output
            assert "Integrated" in result.output

            # Ticket should be closed
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "closed"

            # Session should be done
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "done"

    def test_review_accept_works_when_session_already_done(self) -> None:
        """Accept should succeed when session is 'done' (peasant closed ticket prematurely)."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="done"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                else:
                    result.returncode = 0
                    result.stdout = "Already up to date."
                    result.stderr = ""
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "accepted" in result.output

            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "closed"

    def test_review_accept_allows_logical_feature_checkout_mismatch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", ticket="kin-test"),
            )

            merge_seen = False

            def mock_run(cmd, **kwargs):
                nonlocal merge_seen
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = "master\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                elif cmd == ["git", "merge", "ticket/kin-test", "--no-edit"]:
                    merge_seen = True
                    result.returncode = 0
                    result.stdout = "Merge made by the 'ort' strategy."
                    result.stderr = ""
                elif cmd == ["git", "branch", "-D", "ticket/kin-test"]:
                    result.returncode = 0
                    result.stdout = "Deleted branch ticket/kin-test"
                    result.stderr = ""
                else:
                    raise AssertionError(f"Unexpected subprocess call: {cmd}")
                return result

            with (
                patch("kingdom.cli.subprocess.run", side_effect=mock_run),
                patch("kingdom.cli.peasant.remove_worktree"),
            ):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert merge_seen
            assert "ticket/kin-test" in result.output
            assert "master" in result.output

    def test_review_accept_rejects_session_for_unrelated_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", ticket="kin-other"),
            )

            with patch("kingdom.cli.subprocess.run") as mock_run:
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 1
            assert "records ticket 'kin-other'" in result.output
            assert "kd peasant review kin-test" in result.output
            mock_run.assert_not_called()

    def test_review_accept_rejects_duplicate_sessions_across_features(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")
            ensure_branch_layout(base, BRANCH_B)

            session_name = "peasant-kin-test"
            for feature in (BRANCH, BRANCH_B):
                set_agent_state(
                    base,
                    feature,
                    session_name,
                    AgentState(name=session_name, status="needs_king_review", ticket="kin-test"),
                )

            with patch("kingdom.cli.subprocess.run") as mock_run:
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 1
            assert "multiple Kingdom features" in result.output
            assert normalize_branch_name(BRANCH) in result.output
            assert normalize_branch_name(BRANCH_B) in result.output
            assert "kd peasant accept kin-test" in result.output
            mock_run.assert_not_called()

    def test_accept_slash_branch_with_stored_name(self) -> None:
        """Accept should work for branches with slashes when state.json has the original name."""
        slash_branch = "jrb/my-feature"
        normalized = normalize_branch_name(slash_branch)

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, slash_branch)
            set_current_run(base, slash_branch)

            # Store original branch name in state.json (like kd start does)
            from kingdom.state import branch_root, read_json, write_json

            state_path = branch_root(base, slash_branch) / "state.json"
            state = read_json(state_path)
            state["branch"] = slash_branch
            write_json(state_path, state)

            # Create ticket and session
            tickets_dir = base / ".kd" / "branches" / normalized / "tickets"
            tickets_dir.mkdir(parents=True, exist_ok=True)
            ticket = Ticket(id="slash-test", title="Slash branch test", status="in_review")
            write_ticket(ticket, tickets_dir / "slash-test.md")

            session_name = "peasant-slash-test"
            set_agent_state(
                base,
                slash_branch,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{slash_branch}\n"  # git returns original name with slash
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                else:
                    result.returncode = 0
                    result.stdout = "Already up to date."
                    result.stderr = ""
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "slash-test"])

            assert result.exit_code == 0, result.output
            assert "accepted" in result.output

    def test_review_accept_hand_mode_skips_merge(self) -> None:
        """In hand mode, --accept should skip merge and close ticket directly."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", hand_mode=True),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                else:
                    # Should NOT be called for merge in hand mode
                    raise AssertionError("Unexpected subprocess call in hand mode accept")
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Hand mode" in result.output
            assert "accepted" in result.output

            # Ticket should be closed
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "closed"

            # Session should be done
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "done"

    def test_review_reject_hand_mode_relaunches_in_place(self) -> None:
        """In hand mode, --reject should relaunch using base dir, not worktree."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")
            setup_work_thread(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", agent_backend="claude", hand_mode=True),
            )

            with patch("kingdom.cli.launch_work_background", return_value=77777) as mock_launch:
                result = runner.invoke(peasant_app, ["reject", "kin-test", "try again"])

            assert result.exit_code == 0, result.output
            assert "rejected" in result.output
            assert "relaunched" in result.output

            # launch should have been called with base as worktree (not .kd/worktrees/...)
            mock_launch.assert_called_once()
            call_args = mock_launch.call_args
            worktree_arg = call_args[0][4] if len(call_args[0]) > 4 else call_args[1].get("worktree_path")
            assert worktree_arg == base, f"Expected base dir {base}, got {worktree_arg}"

            # Bounce count should be reset
            state = get_agent_state(base, BRANCH, session_name)
            assert state.review_bounce_count == 0

    def test_review_reject_relaunches_dead_peasant(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")
            thread_id = setup_work_thread(base)

            # Create worktree directory so reject can relaunch
            worktree_dir = base / ".kd" / "worktrees" / "kin-test"
            worktree_dir.mkdir(parents=True, exist_ok=True)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", agent_backend="claude"),
            )

            with patch("kingdom.cli.launch_work_background", return_value=54321) as mock_launch:
                result = runner.invoke(peasant_app, ["reject", "kin-test", "fix the edge case"])

            assert result.exit_code == 0, result.output
            assert "rejected" in result.output
            assert "relaunched" in result.output
            assert "54321" in result.output

            # Ticket should be back to in_progress
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "in_progress"

            # Feedback should be in the thread
            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 1
            assert "fix the edge case" in messages[0].body

            # Session should be working with new PID and reset bounce count
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "working"
            assert state.pid == 54321
            assert state.review_bounce_count == 0

            # launch_harness should have been called
            mock_launch.assert_called_once()

    def test_review_reject_blocks_on_live_pid(self) -> None:
        """When the old peasant PID is still alive, reject should refuse to relaunch."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")
            setup_work_thread(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", pid=os.getpid(), agent_backend="claude"),
            )

            result = runner.invoke(peasant_app, ["reject", "kin-test", "fix it"])

            assert result.exit_code == 1
            assert "still alive" in result.output

    def test_review_reject_no_resume_flag(self) -> None:
        """--no-resume sends feedback without relaunching the peasant."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")
            thread_id = setup_work_thread(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            with patch("kingdom.cli.launch_work_background") as mock_launch:
                result = runner.invoke(
                    peasant_app,
                    ["reject", "kin-test", "try again", "--no-resume"],
                )

            assert result.exit_code == 0, result.output
            assert "rejected" in result.output
            assert "stopped" in result.output
            assert "relaunched" not in result.output

            # Should NOT have relaunched
            mock_launch.assert_not_called()

            # Ticket should be back to in_progress
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "in_progress"

            # Session should be stopped, not working
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "stopped"

            # Feedback should still be in the thread
            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 1
            assert "try again" in messages[0].body

    def test_review_diff_error_shown(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="done"),
            )

            with patch("subprocess.run") as mock_run:
                diff_result = MagicMock()
                diff_result.returncode = 128
                diff_result.stdout = ""
                diff_result.stderr = "fatal: bad revision 'HEAD...ticket/kin-test'"

                mock_run.return_value = diff_result

                result = runner.invoke(peasant_app, ["review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "diff error" in result.output
            assert "fatal" in result.output

    def test_review_flags_no_diff(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="done"),
            )

            with patch("subprocess.run") as mock_run:
                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = ""
                diff_result.stderr = ""

                mock_run.return_value = diff_result

                result = runner.invoke(peasant_app, ["review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "No code diff" in result.output

    def test_review_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["review", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_review_accept_rejects_wrong_ticket_status(self) -> None:
        """--accept should fail if ticket is not in_review."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_progress")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 1
            assert "in_progress" in result.output
            assert "in_review" in result.output

    def test_review_accept_rejects_wrong_session_status(self) -> None:
        """--accept should fail if session is not needs_king_review or done."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="working"),
            )

            result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 1
            assert "working" in result.output
            assert "needs_king_review" in result.output

    def test_review_reject_rejects_wrong_ticket_status(self) -> None:
        """--reject should fail if ticket is not in_review."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="open")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            result = runner.invoke(peasant_app, ["reject", "kin-test", "nope"])

            assert result.exit_code == 1
            assert "open" in result.output
            assert "in_review" in result.output

    def test_review_accept_merge_failure_keeps_in_review(self) -> None:
        """If git merge fails, ticket should stay in_review with recovery steps."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            # Create worktree directory for recovery instructions
            worktree_dir = base / ".kd" / "worktrees" / "kin-test"
            worktree_dir.mkdir(parents=True, exist_ok=True)

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            call_count = 0

            def mock_run(cmd, **kwargs):
                nonlocal call_count
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    # Branch not yet merged
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    # Clean working tree
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                else:
                    # git merge — simulate conflict
                    result.returncode = 1
                    result.stdout = "CONFLICT (content): Merge conflict in src/foo.py"
                    result.stderr = "Automatic merge failed; fix conflicts and then commit the result."
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 1
            assert "Integration failed" in result.output
            assert "Recovery steps" in result.output
            assert "CONFLICT" in result.output
            # Recovery steps should reference the feature branch, not the worktree
            assert "Resolve conflict markers" in result.output
            assert "git add" in result.output
            assert "re-run" in result.output

            # Ticket should still be in_review
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "in_review"

    def test_review_accept_already_merged_skips_merge(self) -> None:
        """If the ticket branch is already merged, accept should skip merge and do cleanup."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    # Branch already merged
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and cmd[:3] == ["git", "branch", "-D"]:
                    result.returncode = 0
                    result.stdout = "Deleted branch ticket/kin-test"
                    result.stderr = ""
                else:
                    raise AssertionError(f"Unexpected subprocess call: {cmd}")
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "already merged" in result.output
            assert "accepted" in result.output

            # Ticket should be closed
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "closed"

            # Session should be done
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "done"

    def test_review_accept_removes_worktree_and_deletes_branch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            branch_delete_seen = False

            def mock_run(cmd, **kwargs):
                nonlocal branch_delete_seen
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and cmd == ["git", "branch", "-D", "ticket/kin-test"]:
                    assert kwargs["timeout"] == 10
                    branch_delete_seen = True
                    result.returncode = 0
                    result.stdout = "Deleted branch ticket/kin-test"
                    result.stderr = ""
                else:
                    raise AssertionError(f"Unexpected subprocess call: {cmd}")
                return result

            with (
                patch("kingdom.cli.subprocess.run", side_effect=mock_run),
                patch("kingdom.cli.peasant.remove_worktree") as mock_remove,
            ):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            mock_remove.assert_called_once_with(
                base,
                "kin-test",
                git_root=base,
                feature=normalize_branch_name(BRANCH),
            )
            assert branch_delete_seen
            assert "Removed worktree" in result.output
            assert "Deleted branch ticket/kin-test" in result.output

    def test_review_accept_cleanup_failure_warns_but_succeeds(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and cmd == ["git", "branch", "-D", "ticket/kin-test"]:
                    assert kwargs["timeout"] == 10
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = "branch not found"
                else:
                    raise AssertionError(f"Unexpected subprocess call: {cmd}")
                return result

            with (
                patch("kingdom.cli.subprocess.run", side_effect=mock_run),
                patch("kingdom.cli.peasant.remove_worktree", side_effect=RuntimeError("boom")),
            ):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Warning: could not remove worktree" in result.output
            assert "Warning: could not delete branch ticket/kin-test" in result.output
            assert "accepted" in result.output

    def test_review_accept_uncommitted_changes_blocks(self) -> None:
        """Accept should refuse to merge if there are uncommitted changes."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    # Branch not yet merged
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    # Dirty working tree
                    result.returncode = 0
                    result.stdout = " M src/foo.py\n M src/bar.py\n"
                    result.stderr = ""
                else:
                    raise AssertionError(f"Unexpected subprocess call: {cmd}")
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 1
            assert "Uncommitted changes" in result.output
            assert "commit or stash" in result.output

            # Ticket should still be in_review
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "in_review"

    def test_review_accept_ignores_kd_only_uncommitted_changes(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            def mock_run(cmd, **kwargs):
                result = MagicMock()
                if cmd and "rev-parse" in cmd and "--abbrev-ref" in cmd:
                    result.returncode = 0
                    result.stdout = f"{BRANCH}\n"
                    result.stderr = ""
                elif cmd and "merge-base" in cmd and "--is-ancestor" in cmd:
                    result.returncode = 1
                    result.stdout = ""
                    result.stderr = ""
                elif cmd and "status" in cmd and "--porcelain" in cmd:
                    result.returncode = 0
                    result.stdout = " M .kd/branches/feature-peasant-test/tickets/kin-test.md\n"
                    result.stderr = ""
                else:
                    result.returncode = 0
                    result.stdout = "Merge made by the 'ort' strategy."
                    result.stderr = ""
                return result

            with patch("kingdom.cli.subprocess.run", side_effect=mock_run):
                result = runner.invoke(peasant_app, ["accept", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "accepted" in result.output
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "closed"

    def test_review_shows_council_feedback(self) -> None:
        """Review info should include council member messages from the work thread."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            ticket_path = create_test_ticket(base, status="in_review")

            from kingdom.harness import append_worklog

            append_worklog(ticket_path, "Implemented the feature")

            thread_id = setup_work_thread(base)
            # Add council feedback messages to the thread
            add_message(base, BRANCH, thread_id, from_="claude", to="all", body="Looks good.\n\nVERDICT: APPROVED")
            add_message(base, BRANCH, thread_id, from_="codex", to="all", body="Minor issue.\n\nVERDICT: APPROVED")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review", review_bounce_count=1),
            )

            with patch("subprocess.run") as mock_run:
                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = " src/foo.py | 5 ++-\n 1 file changed"
                diff_result.stderr = ""

                mock_run.return_value = diff_result

                result = runner.invoke(peasant_app, ["review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Council Feedback" in result.output
            assert "Looks good" in result.output
            assert "Minor issue" in result.output
            assert "in_review" in result.output
            assert "needs_king_review" in result.output
            assert "Review bounces: 1" in result.output
            assert "kd peasant accept" in result.output

    def test_review_warns_on_no_diff(self) -> None:
        """Review should warn when peasant reports done but has no code changes."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, status="in_review")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="needs_king_review"),
            )

            with patch("subprocess.run") as mock_run:
                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = ""  # No diff
                diff_result.stderr = ""

                mock_run.return_value = diff_result

                result = runner.invoke(peasant_app, ["review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "no code diff" in result.output.lower()
            assert "Warning" in result.output


class TestBacklogAutoPull:
    def test_start_moves_backlog_ticket_to_branch(self) -> None:
        """A ticket in backlog should be moved to the branch tickets dir on peasant start."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create ticket directly in backlog
            backlog_tickets = backlog_root(base) / "tickets"
            backlog_tickets.mkdir(parents=True, exist_ok=True)
            ticket = Ticket(
                id="kin-back",
                status="open",
                title="Backlog ticket",
                body="From backlog.\n\n## Acceptance\n\n- [ ] Done",
                created=datetime.now(UTC),
            )
            backlog_path = backlog_tickets / "kin-back.md"
            write_ticket(ticket, backlog_path)

            # Verify it's findable in the backlog
            assert backlog_path.exists()

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-back"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[]),
            ):
                result = runner.invoke(peasant_app, ["start", "kin-back"])

            assert result.exit_code == 0, result.output

            # Backlog copy should be gone
            assert not backlog_path.exists()

            # Ticket should now live under branch tickets
            branch_tickets = base / ".kd" / "branches" / "feature-peasant-test" / "tickets"
            new_path = branch_tickets / "kin-back.md"
            assert new_path.exists()

            # Should still be findable
            found = find_ticket(base, "kin-back")
            assert found is not None
            assert found[0].id == "kin-back"

    def test_auto_pulled_ticket_visible_in_tk_list(self) -> None:
        """After auto-pull, the ticket should appear in `kd tk list`."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create ticket in backlog
            backlog_tickets = backlog_root(base) / "tickets"
            backlog_tickets.mkdir(parents=True, exist_ok=True)
            ticket = Ticket(
                id="kin-list",
                status="open",
                title="Listable ticket",
                body="Should show in list.\n\n## Acceptance\n\n- [ ] Listed",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, backlog_tickets / "kin-list.md")

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with (
                patch("kingdom.cli.peasant.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-list"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
                patch("kingdom.cli.peasant.check_uncommitted_changes", return_value=[]),
            ):
                runner.invoke(peasant_app, ["start", "kin-list"])

            # kd tk list should now show the ticket
            result = runner.invoke(ticket_app, ["list"])
            assert result.exit_code == 0, result.output
            assert "kin-list" in result.output
            assert "Listable ticket" in result.output


class TestPeasantStatusNewStatuses:
    """Tests for awaiting_council and needs_king_review in peasant status display."""

    def test_awaiting_council_shown_in_status(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(
                    name="peasant-kin-test",
                    status="awaiting_council",
                    ticket="kin-test",
                    agent_backend="claude",
                ),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            assert "awaiting_council" in result.output

    def test_needs_king_review_shown_in_status(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-test",
                AgentState(
                    name="peasant-kin-test",
                    status="needs_king_review",
                    ticket="kin-test",
                    agent_backend="codex",
                ),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            # Must appear in the active table (with ticket ID), not just in hidden summary
            assert "kin-test" in result.output
            assert "needs_king_review" in result.output
            assert "No active peasants" not in result.output


class TestPeasantStatusFiltering:
    """Tests for hiding terminal sessions by default."""

    def test_terminal_sessions_hidden_by_default(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create a working peasant and a done peasant
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-active",
                AgentState(
                    name="peasant-kin-active",
                    status="working",
                    ticket="kin-active",
                    agent_backend="claude_code",
                ),
            )
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-done",
                AgentState(
                    name="peasant-kin-done",
                    status="done",
                    ticket="kin-done",
                    agent_backend="claude_code",
                ),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            assert "kin-active" in result.output
            assert "kin-done" not in result.output
            assert "1 done" in result.output

    def test_all_flag_shows_terminal_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-active",
                AgentState(
                    name="peasant-kin-active",
                    status="working",
                    ticket="kin-active",
                    agent_backend="claude_code",
                ),
            )
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-done",
                AgentState(
                    name="peasant-kin-done",
                    status="done",
                    ticket="kin-done",
                    agent_backend="claude_code",
                ),
            )

            result = runner.invoke(peasant_app, ["status", "--all"])
            assert result.exit_code == 0
            assert "kin-active" in result.output
            assert "kin-done" in result.output

    def test_only_terminal_sessions_shows_count(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-done",
                AgentState(
                    name="peasant-kin-done",
                    status="done",
                    ticket="kin-done",
                    agent_backend="claude_code",
                ),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            assert "No active peasants" in result.output
            assert "1 done" in result.output


class TestPeasantStatusBreakdown:
    """Tests for showing done/failed/stopped breakdown instead of just 'completed'."""

    def test_shows_breakdown_with_failed(self) -> None:
        """When hidden peasants include failures, show the breakdown not just 'completed'."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-done",
                AgentState(name="peasant-kin-done", status="done", ticket="kin-done", agent_backend="claude_code"),
            )
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-fail",
                AgentState(name="peasant-kin-fail", status="failed", ticket="kin-fail", agent_backend="claude_code"),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            assert "failed" in result.output.lower()

    def test_shows_breakdown_with_stopped(self) -> None:
        """When hidden peasants include stopped, show the breakdown."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-stop",
                AgentState(name="peasant-kin-stop", status="stopped", ticket="kin-stop", agent_backend="claude_code"),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            assert "stopped" in result.output.lower()

    def test_all_done_shows_done_count(self) -> None:
        """When all hidden peasants are done (no failures), just show 'N done'."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-done",
                AgentState(name="peasant-kin-done", status="done", ticket="kin-done", agent_backend="claude_code"),
            )

            result = runner.invoke(peasant_app, ["status"])
            assert result.exit_code == 0
            # Should not say "completed" — should say "done"
            assert "1 done" in result.output


class TestPeasantNoResultsMessages:
    """Tests for helpful empty-state messages with next-step guidance."""

    def test_peasant_status_empty_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["status"])

            assert result.exit_code == 0
            assert "No active peasants" in result.output
            assert "kd peasant start" in result.output

    def test_peasant_read_no_messages_shows_context(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base, "kin-rd01")

            # Create work thread but no peasant messages
            create_thread(base, BRANCH, "kin-rd01-work", ["peasant-kin-rd01", "king"], "work")
            add_message(base, BRANCH, "kin-rd01-work", from_="king", to="peasant-kin-rd01", body="Do the thing")

            result = runner.invoke(peasant_app, ["read", "kin-rd01"])

            assert result.exit_code == 0
            assert "No messages from" in result.output
            assert "may still be working" in result.output


class TestProjectRootDiscovery:
    """Peasant commands resolve .kd/ state from subdirectories."""

    def test_invocation_git_root_ignores_nested_git_repo_inside_project(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        (tmp_path / ".git").mkdir()

        nested_repo = tmp_path / "vendor" / "nested"
        nested_repo.mkdir(parents=True)
        (nested_repo / ".git").mkdir()

        with patch("kingdom.cli.peasant.Path.cwd", return_value=nested_repo):
            assert resolve_invocation_git_root(tmp_path) == tmp_path

    def test_peasant_command_from_subdirectory(self, tmp_path: Path) -> None:
        """resolve_peasant_context finds .kd/ at repo root when invoked from a subdirectory."""
        setup_project(tmp_path)
        create_test_ticket(tmp_path)

        subdir = tmp_path / "src" / "deep" / "nested"
        subdir.mkdir(parents=True)

        # From repo root (cwd = tmp_path)
        with patch("kingdom.state.Path.cwd", return_value=tmp_path):
            ctx_root = resolve_peasant_context("kin-test")

        # From nested subdirectory (cwd = subdir, should walk up to tmp_path)
        with patch("kingdom.state.Path.cwd", return_value=subdir):
            ctx_sub = resolve_peasant_context("kin-test")

        assert ctx_root.base == ctx_sub.base == tmp_path
        assert ctx_root.full_ticket_id == ctx_sub.full_ticket_id
        assert ctx_root.ticket.title == ctx_sub.ticket.title


class TestPollWorktree:
    """Unit tests for poll_worktree flag→verb mapping."""

    def test_maps_flags_to_verbs(self, tmp_path: Path) -> None:
        git_output = "M  src/foo.py\nA  tests/bar.py\n?? newfile.txt\nD  old.py\nR  renamed.py\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=git_output)
            from kingdom.cli.peasant import poll_worktree

            result = poll_worktree(tmp_path)

        assert result == [
            "Editing src/foo.py",
            "Created tests/bar.py",
            "New file newfile.txt",
            "Deleted old.py",
            "Renamed renamed.py",
        ]

    def test_returns_none_for_clean_worktree(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            from kingdom.cli.peasant import poll_worktree

            assert poll_worktree(tmp_path) is None

    def test_returns_none_for_missing_worktree(self) -> None:
        from kingdom.cli.peasant import poll_worktree

        assert poll_worktree(Path("/nonexistent/path")) is None

    def test_unknown_flag_passes_through(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="C  copied.py\n")
            from kingdom.cli.peasant import poll_worktree

            result = poll_worktree(tmp_path)

        assert result == ["C copied.py"]


class TestPollHeadCommit:
    """Unit tests for poll_head_commit SHA/subject parsing."""

    def test_parses_sha_and_subject(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="a1b2c3d Add feature\n")
            from kingdom.cli.peasant import poll_head_commit

            result = poll_head_commit(tmp_path)

        assert result == ("a1b2c3d", "Add feature")

    def test_returns_none_for_missing_worktree(self) -> None:
        from kingdom.cli.peasant import poll_head_commit

        assert poll_head_commit(Path("/nonexistent/path")) is None

    def test_returns_none_on_failure(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            from kingdom.cli.peasant import poll_head_commit

            assert poll_head_commit(tmp_path) is None

    def test_handles_subject_with_spaces(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="f00baa Fix the broken thing\n")
            from kingdom.cli.peasant import poll_head_commit

            result = poll_head_commit(tmp_path)

        assert result == ("f00baa", "Fix the broken thing")


class TestWatchRichRendering:
    """Regression test: bracketed timestamps and paths survive Rich printing with markup=False."""

    def test_markup_false_preserves_s_tag(self) -> None:
        """With markup=False, [s] is printed literally — not parsed as strikethrough."""
        import re
        from io import StringIO

        from rich.console import Console

        # [s] is Rich's strikethrough tag. With highlight=False (old code), Rich
        # still parses markup, so "[s]rc/..." silently eats the 's'. markup=False
        # prevents this.
        buf = StringIO()
        console = Console(file=buf, width=120, force_terminal=True)
        console.print("  [09:10] [s]rc/kingdom/cli/council.py", markup=False)

        # Strip ANSI to check plain text content
        plain = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
        assert "[09:10]" in plain
        assert "[s]rc/kingdom" in plain  # literal [s], not consumed as style

    def test_highlight_false_would_eat_s_tag(self) -> None:
        """Prove the bug: highlight=False still parses [s] as strikethrough markup."""
        import re
        from io import StringIO

        from rich.console import Console

        buf = StringIO()
        console = Console(file=buf, width=120, force_terminal=True)
        console.print("  [09:10] [s]rc/kingdom/cli/council.py", highlight=False)

        # Strip ANSI — [s] was consumed as a style tag, so the literal "[s]" is gone
        plain = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
        assert "[s]rc/kingdom" not in plain

    def test_committed_line_preserves_brackets(self) -> None:
        from io import StringIO

        from rich.console import Console

        buf = StringIO()
        console = Console(file=buf, width=120)

        console.print('  [09:54] Committed a1b2c3d "Add feature"', markup=False)

        output = buf.getvalue()
        assert "[09:54]" in output
        assert "a1b2c3d" in output


class TestFilterAgentLogLines:
    """Tests for filter_agent_log_lines in peasant watch."""

    def test_filters_json_lines(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = ['{"type": "result", "session_id": "abc"}', "Human readable text"]
        result = filter_agent_log_lines(lines)
        assert result == ["Human readable text"]

    def test_filters_ansi_escapes(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = ["\x1b[32mColored text\x1b[0m"]
        result = filter_agent_log_lines(lines)
        assert result == ["Colored text"]

    def test_filters_box_drawing(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = ["╭── header ──╮", "│ content │", "╰── footer ──╯", "Actual output"]
        result = filter_agent_log_lines(lines)
        assert result == ["Actual output"]

    def test_truncates_long_lines(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = ["A" * 300]
        result = filter_agent_log_lines(lines, max_chars=50)
        assert len(result) == 1
        assert len(result[0]) == 53  # 50 + "..."
        assert result[0].endswith("...")

    def test_returns_last_n_lines(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = [f"line {i}" for i in range(10)]
        result = filter_agent_log_lines(lines, max_lines=3)
        assert result == ["line 7", "line 8", "line 9"]

    def test_empty_input(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        assert filter_agent_log_lines([]) == []

    def test_skips_short_lines(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = ["ab", "Good content here"]
        result = filter_agent_log_lines(lines)
        assert result == ["Good content here"]

    def test_invalid_json_not_filtered(self) -> None:
        from kingdom.cli.peasant import filter_agent_log_lines

        lines = ["{not valid json}"]
        result = filter_agent_log_lines(lines)
        assert result == ["{not valid json}"]

    def test_skips_ndjson_even_with_backend(self) -> None:
        """filter_agent_log_lines skips all JSON — NDJSON is handled by reassemble_stream_text."""
        import json

        from kingdom.cli.peasant import filter_agent_log_lines

        event = {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello from agent"}},
            "session_id": "s1",
        }
        lines = [json.dumps(event)]
        result = filter_agent_log_lines(lines)
        assert result == []

    def test_skips_non_text_ndjson_events(self) -> None:
        """Non-text NDJSON events (like result metadata) are still skipped."""
        import json

        from kingdom.cli.peasant import filter_agent_log_lines

        event = {"type": "result", "session_id": "s1"}
        lines = [json.dumps(event)]
        result = filter_agent_log_lines(lines)
        assert result == []

    def test_no_backend_skips_all_json(self) -> None:
        """JSON lines are always skipped (NDJSON is handled by reassemble_stream_text)."""
        import json

        from kingdom.cli.peasant import filter_agent_log_lines

        event = {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
        }
        lines = [json.dumps(event)]
        result = filter_agent_log_lines(lines)
        assert result == []


class TestPollCouncilStatus:
    def test_ignores_unrelated_branch_council_threads(self) -> None:
        from kingdom.cli.peasant import poll_council_status

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            work_thread_id = setup_work_thread(base)

            create_thread(base, BRANCH, "council-stale", ["king", "claude", "codex"], "council")
            stale_dir = thread_dir(base, BRANCH, "council-stale")
            (stale_dir / ".stream-claude.jsonl").write_text('{"type":"event"}\n')
            (stale_dir / ".stream-codex.jsonl").write_text('{"type":"event"}\n')
            add_message(base, BRANCH, "council-stale", from_="king", to="all", body="hi")
            add_message(base, BRANCH, "council-stale", from_="claude", to="king", body="ok")
            add_message(base, BRANCH, "council-stale", from_="codex", to="king", body="*Error: Exit code 1*")

            assert poll_council_status(base, BRANCH, work_thread_id) is None

    def test_uses_ticket_work_thread_only(self) -> None:
        from kingdom.cli.peasant import poll_council_status

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            work_thread_id = setup_work_thread(base)
            work_dir = thread_dir(base, BRANCH, work_thread_id)

            add_message(base, BRANCH, work_thread_id, from_="king", to="council", body="review this")
            add_message(base, BRANCH, work_thread_id, from_="claude", to="king", body="Looks good", status="complete")
            (work_dir / ".stream-codex.jsonl").write_text('{"type":"event"}\n')

            create_thread(base, BRANCH, "council-stale", ["king", "claude", "codex"], "council")
            stale_dir = thread_dir(base, BRANCH, "council-stale")
            (stale_dir / ".stream-claude.jsonl").write_text('{"type":"event"}\n')
            (stale_dir / ".stream-codex.jsonl").write_text('{"type":"event"}\n')
            add_message(base, BRANCH, "council-stale", from_="king", to="all", body="old question")
            add_message(
                base, BRANCH, "council-stale", from_="codex", to="king", body="*Error: Exit code 1*", status="error"
            )

            result = poll_council_status(base, BRANCH, work_thread_id)
            assert result == "Awaiting council response — claude responded, codex running"


class TestReassembleStreamText:
    """Tests for reassemble_stream_text — NDJSON delta accumulation."""

    def _make_claude_delta(self, text: str) -> str:
        import json

        return json.dumps(
            {
                "type": "stream_event",
                "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
                "session_id": "s1",
            }
        )

    def test_fragments_reassembled_into_sentence(self) -> None:
        """Multiple small deltas become one coherent sentence."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [
            self._make_claude_delta("I'm reading "),
            self._make_claude_delta("the file to "),
            self._make_claude_delta("understand the function. "),
            self._make_claude_delta("Let me check the tests next.\n"),
        ]
        display, remaining = reassemble_stream_text("", lines, "claude_code")
        assert len(display) == 2
        assert "reading the file to understand the function" in display[0]
        assert "check the tests next" in display[1]
        assert remaining == ""

    def test_newline_boundaries_split_lines(self) -> None:
        """Newlines in stream text produce separate display lines."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [
            self._make_claude_delta("First line of output.\n"),
            self._make_claude_delta("Second line of output.\n"),
        ]
        display, _remaining = reassemble_stream_text("", lines, "claude_code")
        assert len(display) == 2
        assert "First line" in display[0]
        assert "Second line" in display[1]

    def test_short_fragments_buffered(self) -> None:
        """Fragments shorter than min_display_len are not shown."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [self._make_claude_delta("Let me")]
        display, remaining = reassemble_stream_text("", lines, "claude_code")
        assert display == []
        assert remaining == "Let me"

    def test_buffer_carries_across_calls(self) -> None:
        """Remaining buffer from one call feeds into the next."""
        from kingdom.cli.peasant import reassemble_stream_text

        # First poll: incomplete sentence
        lines1 = [self._make_claude_delta("I'm reading the ")]
        display1, buf = reassemble_stream_text("", lines1, "claude_code")
        assert display1 == []
        assert "reading" in buf

        # Second poll: sentence completes
        lines2 = [self._make_claude_delta("harness code to understand the flow.\n")]
        display2, buf = reassemble_stream_text(buf, lines2, "claude_code")
        assert len(display2) == 1
        assert "reading the harness code" in display2[0]
        assert buf == ""

    def test_flush_emits_remaining(self) -> None:
        """flush=True emits whatever is in the buffer regardless of length."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [self._make_claude_delta("Almost done")]
        display, remaining = reassemble_stream_text("", lines, "claude_code", flush=True)
        assert display == ["Almost done"]
        assert remaining == ""

    def test_no_backend_returns_empty(self) -> None:
        """Without a backend, no text is extracted."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [self._make_claude_delta("Hello")]
        display, remaining = reassemble_stream_text("", lines, "")
        assert display == []
        assert remaining == ""

    def test_non_text_events_ignored(self) -> None:
        """Non-text NDJSON events don't contribute to the buffer."""
        import json

        from kingdom.cli.peasant import reassemble_stream_text

        event = json.dumps({"type": "result", "session_id": "s1"})
        display, remaining = reassemble_stream_text("", [event], "claude_code")
        assert display == []
        assert remaining == ""

    def test_mixed_ndjson_and_plain_text(self) -> None:
        """Plain text lines are ignored by reassemble (handled by filter_agent_log_lines)."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [
            "Some plain text output",
            self._make_claude_delta("Reading the source code now.\n"),
        ]
        display, _remaining = reassemble_stream_text("", lines, "claude_code")
        # Only the NDJSON text should appear
        assert len(display) == 1
        assert "Reading the source code" in display[0]

    def test_sentence_boundaries_within_line(self) -> None:
        """Sentence-ending punctuation splits long text within a single line."""
        from kingdom.cli.peasant import reassemble_stream_text

        lines = [
            self._make_claude_delta(
                "I found the bug in the parser. It was missing a null check. Let me fix it now and commit.\n"
            ),
        ]
        display, _remaining = reassemble_stream_text("", lines, "claude_code")
        assert len(display) == 3
        assert "bug in the parser" in display[0]
        assert "null check" in display[1]
        assert "fix it now and commit" in display[2]

    def test_truncates_long_lines(self) -> None:
        """Lines exceeding max_chars are truncated with ellipsis."""
        from kingdom.cli.peasant import reassemble_stream_text

        long_text = "A" * 300 + ".\n"
        lines = [self._make_claude_delta(long_text)]
        display, _remaining = reassemble_stream_text("", lines, "claude_code", max_chars=50)
        assert len(display) == 1
        assert display[0].endswith("...")
        assert len(display[0]) == 53


# ---------------------------------------------------------------------------
# Cross-branch peasant resolution
# ---------------------------------------------------------------------------

BRANCH_A = "feature/branch-a"
BRANCH_B = "feature/branch-b"


class TestCrossBranchPeasantContext:
    """Test that resolve_peasant_context finds peasant sessions across branches."""

    def test_resolve_finds_peasant_on_different_branch(self) -> None:
        """Post-start commands resolve context via peasant ownership, not current session."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            # Set up two branches
            ensure_branch_layout(base, BRANCH_A)
            ensure_branch_layout(base, BRANCH_B)

            # Create ticket on branch A
            tickets_dir_a = base / ".kd" / "branches" / normalize_branch_name(BRANCH_A) / "tickets"
            ticket = Ticket(id="abcd", status="in_review", title="Cross-branch test", created=datetime.now(UTC))
            ticket_path = tickets_dir_a / "abcd.md"
            write_ticket(ticket, ticket_path)

            # Create peasant session on branch A
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-abcd",
                AgentState(name="peasant-abcd", status="needs_king_review", ticket="abcd"),
            )

            # Switch active session to branch B
            set_current_run(base, normalize_branch_name(BRANCH_B))

            # resolve_peasant_context should find the peasant on branch A
            ctx = resolve_peasant_context("abcd", base=base)
            assert ctx.feature == normalize_branch_name(BRANCH_A)
            assert ctx.full_ticket_id == "abcd"

    def test_start_still_uses_current_session(self) -> None:
        """peasant start (auto_pull=True) uses the current session, not cross-branch scan."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_B)
            set_current_run(base, normalize_branch_name(BRANCH_B))

            # Create ticket on branch B
            tickets_dir_b = base / ".kd" / "branches" / normalize_branch_name(BRANCH_B) / "tickets"
            ticket = Ticket(id="efgh", status="open", title="Start test", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir_b / "efgh.md")

            ctx = resolve_peasant_context("efgh", base=base, auto_pull=True)
            assert ctx.feature == normalize_branch_name(BRANCH_B)

    def test_falls_back_to_current_session_when_no_peasant_found(self) -> None:
        """When no peasant session exists, falls back to current run."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_current_run(base, normalize_branch_name(BRANCH_A))

            # Create ticket on branch A, no peasant session
            tickets_dir = base / ".kd" / "branches" / normalize_branch_name(BRANCH_A) / "tickets"
            ticket = Ticket(id="nope", status="open", title="No peasant", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "nope.md")

            ctx = resolve_peasant_context("nope", base=base)
            assert ctx.feature == normalize_branch_name(BRANCH_A)

    def test_clean_removes_worktree_from_peasant_owning_branch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            ensure_branch_layout(base, BRANCH_B)

            tickets_dir_a = base / ".kd" / "branches" / normalize_branch_name(BRANCH_A) / "tickets"
            ticket = Ticket(id="abcd", status="in_review", title="Cross-branch clean", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir_a / "abcd.md")
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-abcd",
                AgentState(name="peasant-abcd", status="needs_king_review", ticket="abcd"),
            )
            set_current_run(base, normalize_branch_name(BRANCH_B))

            with patch("kingdom.cli.peasant.remove_worktree") as mock_remove:
                result = runner.invoke(peasant_app, ["clean", "--force", "abcd"])

            assert result.exit_code == 0, result.output
            mock_remove.assert_called_once_with(
                base,
                "abcd",
                git_root=base,
                feature=normalize_branch_name(BRANCH_A),
            )


class TestFindPeasantBranch:
    """Test the find_peasant_branch helper in session.py."""

    def test_finds_active_session(self) -> None:
        from kingdom.session import find_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-xyz",
                AgentState(name="peasant-xyz", status="working", ticket="xyz"),
            )
            result = find_peasant_branch(base, "peasant-xyz")
            assert result == normalize_branch_name(BRANCH_A)

    def test_ignores_idle_sessions(self) -> None:
        from kingdom.session import find_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-idle",
                AgentState(name="peasant-idle", status="idle"),
            )
            result = find_peasant_branch(base, "peasant-idle")
            assert result is None

    def test_returns_none_when_not_found(self) -> None:
        from kingdom.session import find_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            result = find_peasant_branch(base, "peasant-nonexistent")
            assert result is None


class TestCrossBranchPrefixId:
    """Test that prefix ticket IDs work with cross-branch resolution."""

    def test_prefix_id_resolves_cross_branch(self) -> None:
        """A prefix like 'ab' should resolve to the full ID before session lookup."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            ensure_branch_layout(base, BRANCH_B)

            # Create ticket with full ID "abcd" on branch A
            tickets_dir_a = base / ".kd" / "branches" / normalize_branch_name(BRANCH_A) / "tickets"
            ticket = Ticket(id="abcd", status="in_review", title="Prefix test", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir_a / "abcd.md")

            # Create peasant session on branch A with the full ID
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-abcd",
                AgentState(name="peasant-abcd", status="needs_king_review", ticket="abcd"),
            )

            # Switch active session to branch B
            set_current_run(base, normalize_branch_name(BRANCH_B))

            # Use a PREFIX — this is the bug that was reported
            ctx = resolve_peasant_context("ab", base=base)
            assert ctx.feature == normalize_branch_name(BRANCH_A)
            assert ctx.full_ticket_id == "abcd"


class TestFindActivePeasantBranch:
    """Test the find_active_peasant_branch helper in session.py."""

    def test_finds_working_session(self) -> None:
        from kingdom.session import find_active_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-xyz",
                AgentState(name="peasant-xyz", status="working", ticket="xyz"),
            )
            result = find_active_peasant_branch(base, "peasant-xyz")
            assert result == normalize_branch_name(BRANCH_A)

    def test_ignores_done_sessions(self) -> None:
        """Done peasants should not block operations."""
        from kingdom.session import find_active_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-xyz",
                AgentState(name="peasant-xyz", status="done", ticket="xyz"),
            )
            result = find_active_peasant_branch(base, "peasant-xyz")
            assert result is None

    def test_ignores_failed_sessions(self) -> None:
        from kingdom.session import find_active_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-xyz",
                AgentState(name="peasant-xyz", status="failed", ticket="xyz"),
            )
            result = find_active_peasant_branch(base, "peasant-xyz")
            assert result is None

    def test_ignores_stopped_sessions(self) -> None:
        from kingdom.session import find_active_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-xyz",
                AgentState(name="peasant-xyz", status="stopped", ticket="xyz"),
            )
            result = find_active_peasant_branch(base, "peasant-xyz")
            assert result is None

    def test_finds_needs_king_review(self) -> None:
        from kingdom.session import find_active_peasant_branch

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH_A)
            set_agent_state(
                base,
                BRANCH_A,
                "peasant-xyz",
                AgentState(name="peasant-xyz", status="needs_king_review", ticket="xyz"),
            )
            result = find_active_peasant_branch(base, "peasant-xyz")
            assert result == normalize_branch_name(BRANCH_A)


class TestPeasantStatusJson:
    """Tests for kd peasant status --json."""

    def test_status_json_outputs_valid_json(self) -> None:
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            now = datetime.now(UTC).isoformat()
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-042",
                AgentState(
                    name="peasant-kin-042",
                    status="working",
                    pid=99999,
                    ticket="kin-042",
                    agent_backend="claude",
                    started_at=now,
                    last_activity=now,
                ),
            )

            with patch("os.kill"):  # Mock kill so liveness check passes
                result = runner.invoke(peasant_app, ["status", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["ticket"] == "kin-042"
            assert data[0]["status"] == "working"
            assert data[0]["agent"] == "claude"
            assert data[0]["pid"] == 99999
            assert data[0]["started_at"] == now
            assert isinstance(data[0]["elapsed_minutes"], int)

    def test_status_json_reports_dead_for_dead_process(self) -> None:
        """The most critical AC: dead processes must report 'dead', not 'working'."""
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            now = datetime.now(UTC).isoformat()
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-dead",
                AgentState(
                    name="peasant-kin-dead",
                    status="working",
                    pid=99999,
                    ticket="kin-dead",
                    agent_backend="claude",
                    started_at=now,
                    last_activity=now,
                ),
            )

            # Don't mock os.kill — is_process_alive will raise OSError → dead
            result = runner.invoke(peasant_app, ["status", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["status"] == "dead"

    def test_status_json_empty_returns_empty_list(self) -> None:
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(peasant_app, ["status", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data == []


class TestPeasantShowJson:
    """Tests for kd peasant show --json."""

    def test_show_json_outputs_valid_json(self) -> None:
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            ticket_path = create_test_ticket(base)

            # Add worklog
            content = ticket_path.read_text(encoding="utf-8")
            content += "\n\n## Worklog\n\n- [09:00] Started work\n"
            ticket_path.write_text(content, encoding="utf-8")

            # Create agent-live.log with plain text
            peasant_logs_dir = logs_root(base, BRANCH) / "peasant-kin-test"
            peasant_logs_dir.mkdir(parents=True, exist_ok=True)
            (peasant_logs_dir / "agent-live.log").write_text(
                "Reading the source file for context\n",
                encoding="utf-8",
            )

            result = runner.invoke(peasant_app, ["show", "--json", "kin-test"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ticket_id"] == "kin-test"
            assert "Started work" in data["worklog"]
            assert isinstance(data["activity"], list)
            assert isinstance(data["commits"], list)
            assert "status" in data
            assert "hand_mode" in data
