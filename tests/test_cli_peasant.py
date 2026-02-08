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
from kingdom.thread import thread_dir
from kingdom.ticket import Ticket, write_ticket

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
            with patch("kingdom.cli.create_worktree", return_value=base / ".kd" / "worktrees" / "kin-test"), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("os.open", return_value=3), \
                 patch("os.close"):
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

    def test_start_refuses_if_already_running(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            create_test_ticket(base)

            # Set up a "running" session with a live PID
            set_agent_state(
                base, BRANCH, "peasant-kin-test",
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
                base, BRANCH, "peasant-kin-042",
                AgentState(
                    name="peasant-kin-042",
                    status="working",
                    pid=99999,
                    ticket="kin-042",
                    started_at=now,
                    last_activity=now,
                ),
            )

            result = runner.invoke(cli.app, ["peasant", "status"])

            assert result.exit_code == 0
            assert "kin-042" in result.output
            assert "working" in result.output

    def test_status_ignores_non_peasant_sessions(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # A regular agent session (not a peasant)
            set_agent_state(
                base, BRANCH, "claude",
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
                base, BRANCH, "peasant-kin-test",
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
                base, BRANCH, "peasant-kin-test",
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
