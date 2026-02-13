"""Tests for the peasant CLI commands."""

from __future__ import annotations

import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kingdom import cli
from kingdom.session import AgentState, get_agent_state, set_agent_state
from kingdom.state import ensure_branch_layout, logs_root, set_current_run
from kingdom.thread import add_message, create_thread, list_messages, thread_dir
from kingdom.ticket import Ticket, find_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/peasant-test"


def setup_project(base: Path) -> None:
    """Create a minimal project with branch layout and a test ticket."""
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


def create_test_ticket(base: Path, ticket_id: str = "kin-test") -> Path:
    """Create a test ticket and return its path."""
    tickets_dir = base / ".kd" / "branches" / "feature-peasant-test" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket = Ticket(
        id=ticket_id,
        status="open",
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
                patch("kingdom.cli.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"),
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
            ):
                result = runner.invoke(cli.app, ["peasant", "start", "kin-test"])

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
                patch("kingdom.cli.create_worktree") as mock_create_worktree,
                patch("subprocess.Popen", return_value=mock_proc),
                patch("os.open", return_value=3),
                patch("os.close"),
            ):
                result = runner.invoke(cli.app, ["peasant", "start", "kin-test", "--hand"])

            assert result.exit_code == 0, result.output
            assert "Running in hand mode" in result.output
            assert "pid 12345" in result.output

            # create_worktree should NOT be called
            mock_create_worktree.assert_not_called()

            # Session should be created
            state = get_agent_state(base, BRANCH, "peasant-kin-test")
            assert state.status == "working"
            assert state.pid == 12345

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

            result = runner.invoke(cli.app, ["peasant", "start", "kin-test"])

            assert result.exit_code == 1
            assert "already running" in result.output

    def test_start_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "start", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantStatus:
    def test_status_no_peasants(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "status"])

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
                result = runner.invoke(cli.app, ["peasant", "status"])

            assert result.exit_code == 0
            assert "kin-042" in result.output
            assert "working" in result.output
            assert "claude" in result.output

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

            result = runner.invoke(cli.app, ["peasant", "status"])

            assert result.exit_code == 0
            assert "No active peasants" in result.output


class TestPeasantLogs:
    def test_logs_no_logs_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(cli.app, ["peasant", "logs", "kin-test"])

            assert result.exit_code == 1
            assert "No logs found" in result.output

    def test_logs_shows_stdout(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Create log files
            peasant_logs_dir = logs_root(base, BRANCH) / "peasant-kin-test"
            peasant_logs_dir.mkdir(parents=True, exist_ok=True)
            (peasant_logs_dir / "stdout.log").write_text("Hello from peasant\n", encoding="utf-8")
            (peasant_logs_dir / "stderr.log").write_text("", encoding="utf-8")

            result = runner.invoke(cli.app, ["peasant", "logs", "kin-test"])

            assert result.exit_code == 0
            assert "Hello from peasant" in result.output

    def test_logs_shows_stderr(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            peasant_logs_dir = logs_root(base, BRANCH) / "peasant-kin-test"
            peasant_logs_dir.mkdir(parents=True, exist_ok=True)
            (peasant_logs_dir / "stdout.log").write_text("", encoding="utf-8")
            (peasant_logs_dir / "stderr.log").write_text("Error occurred\n", encoding="utf-8")

            result = runner.invoke(cli.app, ["peasant", "logs", "kin-test"])

            assert result.exit_code == 0
            assert "Error occurred" in result.output

    def test_logs_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "logs", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantStop:
    def test_stop_sends_sigterm(self) -> None:
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

            with patch("os.kill") as mock_kill:
                result = runner.invoke(cli.app, ["peasant", "stop", "kin-test"])

            assert result.exit_code == 0
            assert "SIGTERM" in result.output
            mock_kill.assert_called_once_with(99999, signal.SIGTERM)

            # Session should be updated
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

            result = runner.invoke(cli.app, ["peasant", "stop", "kin-test"])

            assert result.exit_code == 1
            assert "not running" in result.output

    def test_stop_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "stop", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantClean:
    def test_clean_removes_worktree(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch("kingdom.cli.remove_worktree") as mock_remove:
                result = runner.invoke(cli.app, ["peasant", "clean", "kin-test"])

            assert result.exit_code == 0
            assert "Removed worktree" in result.output
            mock_remove.assert_called_once_with(base, "kin-test")

    def test_clean_no_worktree(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            with patch("kingdom.cli.remove_worktree", side_effect=FileNotFoundError("No worktree")):
                result = runner.invoke(cli.app, ["peasant", "clean", "kin-test"])

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
                result = runner.invoke(cli.app, ["peasant", "sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Sync complete" in result.output

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

            result = runner.invoke(cli.app, ["peasant", "sync", "kin-test"])

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
                result = runner.invoke(cli.app, ["peasant", "sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "Sync complete" in result.output

    def test_sync_no_worktree(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(cli.app, ["peasant", "sync", "kin-test"])

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
                result = runner.invoke(cli.app, ["peasant", "sync", "kin-test"])

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
                result = runner.invoke(cli.app, ["peasant", "sync", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "init-worktree.sh" in result.output
            assert "Sync complete" in result.output

    def test_sync_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "sync", "kin-nope"])

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

            result = runner.invoke(cli.app, ["peasant", "msg", "kin-test", "focus on tests"])

            assert result.exit_code == 0, result.output
            assert "Directive sent" in result.output

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

            runner.invoke(cli.app, ["peasant", "msg", "kin-test", "first directive"])
            runner.invoke(cli.app, ["peasant", "msg", "kin-test", "second directive"])

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

            result = runner.invoke(cli.app, ["peasant", "msg", "kin-test", "hello"])

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

            result = runner.invoke(cli.app, ["peasant", "msg", "kin-test", "do something"])

            assert result.exit_code == 0, result.output
            assert "Directive sent" in result.output
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

            result = runner.invoke(cli.app, ["peasant", "msg", "kin-test", "keep going"])

            assert result.exit_code == 0, result.output
            assert "Directive sent" in result.output
            assert "Warning" not in result.output

    def test_msg_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "msg", "kin-nope", "hello"])

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

            result = runner.invoke(cli.app, ["peasant", "read", "kin-test"])

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

            result = runner.invoke(cli.app, ["peasant", "read", "kin-test"])

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

            result = runner.invoke(cli.app, ["peasant", "read", "kin-test", "--last", "2"])

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

            result = runner.invoke(cli.app, ["peasant", "read", "kin-test", "--last", "0"])

            assert result.exit_code != 0

    def test_read_last_negative_rejected(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            setup_work_thread(base)

            result = runner.invoke(cli.app, ["peasant", "read", "kin-test", "--last", "-1"])

            assert result.exit_code != 0

    def test_read_no_thread(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(cli.app, ["peasant", "read", "kin-test"])

            assert result.exit_code == 1
            assert "No work thread" in result.output

    def test_read_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "read", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestPeasantReview:
    def test_review_shows_results(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            ticket_path = create_test_ticket(base)

            # Add a worklog to the ticket
            from kingdom.harness import append_worklog

            append_worklog(ticket_path, "Did some work")

            session_name = "peasant-kin-test"
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="done"),
            )

            with (
                patch("subprocess.run") as mock_run,
            ):
                # pytest result
                pytest_result = MagicMock()
                pytest_result.returncode = 0
                pytest_result.stdout = "5 passed"
                pytest_result.stderr = ""

                # ruff result
                ruff_result = MagicMock()
                ruff_result.returncode = 0
                ruff_result.stdout = ""
                ruff_result.stderr = ""

                # git diff result
                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = " src/foo.py | 5 ++-\n 1 file changed"
                diff_result.stderr = ""

                mock_run.side_effect = [pytest_result, ruff_result, diff_result]

                result = runner.invoke(cli.app, ["peasant", "review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "PASSED" in result.output
            assert "Did some work" in result.output
            assert "done" in result.output
            assert "--accept" in result.output

    def test_review_accept_closes_ticket(self) -> None:
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

            result = runner.invoke(cli.app, ["peasant", "review", "kin-test", "--accept"])

            assert result.exit_code == 0, result.output
            assert "accepted" in result.output

            # Ticket should be closed
            ticket_result = find_ticket(base, "kin-test")
            assert ticket_result is not None
            ticket, _ = ticket_result
            assert ticket.status == "closed"

            # Session should be done
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "done"

    def test_review_reject_relaunches_dead_peasant(self) -> None:
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
                AgentState(name=session_name, status="done", agent_backend="claude"),
            )

            with patch("kingdom.cli.launch_work_background", return_value=54321) as mock_launch:
                result = runner.invoke(cli.app, ["peasant", "review", "kin-test", "--reject", "fix the edge case"])

            assert result.exit_code == 0, result.output
            assert "rejected" in result.output
            assert "relaunched" in result.output
            assert "54321" in result.output

            # Feedback should be in the thread
            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 1
            assert "fix the edge case" in messages[0].body

            # Session should be working with new PID
            state = get_agent_state(base, BRANCH, session_name)
            assert state.status == "working"
            assert state.pid == 54321

            # launch_harness should have been called
            mock_launch.assert_called_once()

    def test_review_reject_relaunches_on_stale_pid(self) -> None:
        """PID reuse: status=done but PID happens to be alive (another process). Should still relaunch."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)
            setup_work_thread(base)

            session_name = "peasant-kin-test"
            # Status is "done" but PID is alive (os.getpid()) — simulates PID reuse
            set_agent_state(
                base,
                BRANCH,
                session_name,
                AgentState(name=session_name, status="done", pid=os.getpid(), agent_backend="claude"),
            )

            with patch("kingdom.cli.launch_work_background", return_value=99999) as mock_launch:
                result = runner.invoke(cli.app, ["peasant", "review", "kin-test", "--reject", "fix it"])

            assert result.exit_code == 0, result.output
            assert "relaunched" in result.output
            mock_launch.assert_called_once()

    def test_review_reject_no_relaunch_if_alive(self) -> None:
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
                AgentState(name=session_name, status="working", pid=os.getpid()),
            )

            with patch("kingdom.cli.launch_work_background") as mock_launch:
                result = runner.invoke(cli.app, ["peasant", "review", "kin-test", "--reject", "try again"])

            assert result.exit_code == 0, result.output
            assert "rejected" in result.output
            assert "pick it up" in result.output
            assert "relaunched" not in result.output

            # Should NOT have relaunched
            mock_launch.assert_not_called()

            # Feedback should still be in the thread
            messages = list_messages(base, BRANCH, thread_id)
            assert len(messages) == 1
            assert "try again" in messages[0].body

    def test_review_shows_failures(self) -> None:
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
                pytest_result = MagicMock()
                pytest_result.returncode = 1
                pytest_result.stdout = "FAILED test_foo.py"
                pytest_result.stderr = ""

                ruff_result = MagicMock()
                ruff_result.returncode = 1
                ruff_result.stdout = "E501 line too long"
                ruff_result.stderr = ""

                diff_result = MagicMock()
                diff_result.returncode = 0
                diff_result.stdout = ""
                diff_result.stderr = ""

                mock_run.side_effect = [pytest_result, ruff_result, diff_result]

                result = runner.invoke(cli.app, ["peasant", "review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "FAILED" in result.output
            assert "ISSUES" in result.output
            assert "--reject" in result.output

    def test_review_accept_reject_mutually_exclusive(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            result = runner.invoke(cli.app, ["peasant", "review", "kin-test", "--accept", "--reject", "nope"])

            assert result.exit_code == 1
            assert "mutually exclusive" in result.output

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
                pytest_result = MagicMock()
                pytest_result.returncode = 0
                pytest_result.stdout = "5 passed"
                pytest_result.stderr = ""

                ruff_result = MagicMock()
                ruff_result.returncode = 0
                ruff_result.stdout = ""
                ruff_result.stderr = ""

                diff_result = MagicMock()
                diff_result.returncode = 128
                diff_result.stdout = ""
                diff_result.stderr = "fatal: bad revision 'HEAD...ticket/kin-test'"

                mock_run.side_effect = [pytest_result, ruff_result, diff_result]

                result = runner.invoke(cli.app, ["peasant", "review", "kin-test"])

            assert result.exit_code == 0, result.output
            assert "diff error" in result.output
            assert "fatal" in result.output

    def test_review_ticket_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["peasant", "review", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output
