"""Tests for kingdom.harness module."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kingdom.harness import (
    append_worklog,
    build_prompt,
    extract_worklog,
    extract_worklog_entry,
    get_new_directives,
    parse_status,
    run_agent_loop,
)
from kingdom.session import AgentState, get_agent_state, set_agent_state
from kingdom.state import ensure_branch_layout, set_current_run
from kingdom.thread import add_message, create_thread, list_messages
from kingdom.ticket import Ticket, read_ticket, write_ticket

BRANCH = "feature/harness-test"

# Common mock return values
TESTS_PASS = (True, "4 passed")
TESTS_FAIL = (False, "FAILED test_foo.py::test_bar - AssertionError")
LINT_PASS = (True, "All checks passed!")
LINT_FAIL = (False, "src/foo.py:1:1: F401 `os` imported but unused")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    set_current_run(tmp_path, BRANCH)
    return tmp_path


@pytest.fixture()
def ticket_path(project: Path) -> Path:
    """Create a test ticket."""
    tickets_dir = project / ".kd" / "branches" / "feature-harness-test" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket = Ticket(
        id="kin-test",
        status="open",
        title="Test ticket",
        body="Implement the thing.\n\n## Acceptance\n\n- [ ] It works",
        created=datetime.now(UTC),
    )
    path = tickets_dir / "kin-test.md"
    write_ticket(ticket, path)
    return path


class TestBuildPrompt:
    def test_basic_prompt(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50)
        assert str(ticket_path) in prompt
        assert "iteration 1 of 50" in prompt
        assert "STATUS: DONE" in prompt
        assert "STATUS: BLOCKED" in prompt
        assert "STATUS: CONTINUE" in prompt

    def test_prompt_does_not_contain_ticket_body(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50)
        assert "Do the thing" not in prompt
        assert str(ticket_path) in prompt

    def test_prompt_with_worklog(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "- Did step 1", [], 2, 50)
        assert "Current Worklog" in prompt
        assert "Did step 1" in prompt

    def test_prompt_with_directives(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", ["Focus on tests", "Use pytest"], 3, 50)
        assert "Directives from Lead" in prompt
        assert "Focus on tests" in prompt
        assert "Use pytest" in prompt

    def test_prompt_with_all(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "- Done A", ["Do B"], 5, 50)
        assert str(ticket_path) in prompt
        assert "Done A" in prompt
        assert "Do B" in prompt
        assert "iteration 5 of 50" in prompt

    def test_prompt_with_phase_prompt(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50, phase_prompt="Always write tests first.")
        assert prompt.startswith("Always write tests first.")
        assert "peasant agent" in prompt

    def test_prompt_without_phase_prompt(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50)
        assert prompt.startswith("You are a peasant agent")

    def test_prompt_custom_max_iterations(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 3, 10)
        assert "iteration 3 of 10" in prompt


class TestParseStatus:
    def test_done(self) -> None:
        assert parse_status("I did the thing\n\nSTATUS: DONE") == "done"

    def test_blocked(self) -> None:
        assert parse_status("Need help\n\nSTATUS: BLOCKED") == "blocked"

    def test_continue(self) -> None:
        assert parse_status("Making progress\n\nSTATUS: CONTINUE") == "continue"

    def test_case_insensitive(self) -> None:
        assert parse_status("STATUS: done") == "done"
        assert parse_status("STATUS: Done") == "done"

    def test_no_status_returns_continue(self) -> None:
        assert parse_status("Just some text without status") == "continue"

    def test_empty_string(self) -> None:
        assert parse_status("") == "continue"

    def test_status_in_middle_ignored(self) -> None:
        # Only the last STATUS line counts
        text = "STATUS: DONE\nMore work\nSTATUS: CONTINUE"
        assert parse_status(text) == "continue"


class TestExtractWorklogEntry:
    def test_basic_extraction(self) -> None:
        text = "I implemented the function.\n\nSTATUS: CONTINUE"
        entry = extract_worklog_entry(text)
        assert entry == "I implemented the function."

    def test_multiline_takes_first_paragraph(self) -> None:
        text = "Did step A.\n\nAlso did step B.\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert entry == "Did step A."

    def test_long_entry_truncated(self) -> None:
        text = "x" * 500 + "\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert len(entry) <= 300

    def test_empty_response(self) -> None:
        entry = extract_worklog_entry("")
        assert entry == ""


class TestAppendWorklog:
    def test_creates_worklog_section(self, ticket_path: Path) -> None:
        append_worklog(ticket_path, "Started work")
        ticket = read_ticket(ticket_path)
        assert "## Worklog" in ticket.body
        assert "Started work" in ticket.body

    def test_appends_to_existing_worklog(self, ticket_path: Path) -> None:
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- First entry"
        write_ticket(ticket, ticket_path)

        append_worklog(ticket_path, "Second entry")
        ticket = read_ticket(ticket_path)
        assert "First entry" in ticket.body
        assert "Second entry" in ticket.body

    def test_entry_has_timestamp(self, ticket_path: Path) -> None:
        append_worklog(ticket_path, "Timed entry")
        ticket = read_ticket(ticket_path)
        assert re.search(r"\[\d{2}:\d{2}\]", ticket.body)

    def test_appends_to_end_of_document(self, ticket_path: Path) -> None:
        """Worklog entries append to end of document (worklog is always last section)."""
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- Existing"
        write_ticket(ticket, ticket_path)

        append_worklog(ticket_path, "New entry")
        ticket = read_ticket(ticket_path)

        # New entry should be at the very end
        assert ticket.body.rstrip().endswith("New entry")


class TestExtractWorklog:
    def test_no_worklog(self, ticket_path: Path) -> None:
        assert extract_worklog(ticket_path) == ""

    def test_extracts_worklog(self, ticket_path: Path) -> None:
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- Entry 1\n- Entry 2"
        write_ticket(ticket, ticket_path)

        worklog = extract_worklog(ticket_path)
        assert "Entry 1" in worklog
        assert "Entry 2" in worklog

    def test_returns_everything_after_header(self, ticket_path: Path) -> None:
        """Worklog is always the last section, so everything after header is worklog."""
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- Entry 1\n- Entry 2"
        write_ticket(ticket, ticket_path)

        worklog = extract_worklog(ticket_path)
        assert "Entry 1" in worklog
        assert "Entry 2" in worklog


class TestGetNewDirectives:
    def test_no_new_messages(self, project: Path) -> None:
        create_thread(project, BRANCH, "test-thread", ["peasant", "king"], "work")
        directives, seq = get_new_directives(project, BRANCH, "test-thread", 0)
        assert directives == []
        assert seq == 0

    def test_gets_king_messages(self, project: Path) -> None:
        create_thread(project, BRANCH, "test-thread2", ["peasant", "king"], "work")
        add_message(project, BRANCH, "test-thread2", from_="king", to="peasant", body="Do this")
        add_message(project, BRANCH, "test-thread2", from_="peasant", to="king", body="Done")
        add_message(project, BRANCH, "test-thread2", from_="king", to="peasant", body="Now do that")

        directives, seq = get_new_directives(project, BRANCH, "test-thread2", 0)
        assert len(directives) == 2
        assert "Do this" in directives
        assert "Now do that" in directives
        assert seq == 3

    def test_respects_last_seen(self, project: Path) -> None:
        create_thread(project, BRANCH, "test-thread3", ["peasant", "king"], "work")
        add_message(project, BRANCH, "test-thread3", from_="king", to="peasant", body="Old")
        add_message(project, BRANCH, "test-thread3", from_="king", to="peasant", body="New")

        directives, seq = get_new_directives(project, BRANCH, "test-thread3", 1)
        assert len(directives) == 1
        assert "New" in directives
        assert seq == 2


class TestRunAgentLoop:
    def setup_for_loop(self, project: Path, ticket_path: Path) -> tuple[str, str]:
        """Set up thread and session for a loop test. Returns (thread_id, session_name)."""
        thread_id = "kin-test-work"
        session_name = "peasant-kin-test"
        create_thread(project, BRANCH, thread_id, [session_name, "king"], "work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Start work")
        set_agent_state(project, BRANCH, session_name, AgentState(name=session_name))
        return thread_id, session_name

    def test_loop_done_when_gates_pass(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", return_value=mock_result),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "done"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "done"

        # Worklog should mention quality gates
        ticket = read_ticket(ticket_path)
        assert "quality gates passed" in ticket.body.lower()

    def test_loop_passes_peasant_identity_env(self, project: Path, ticket_path: Path, monkeypatch) -> None:
        """Backend subprocess should receive peasant identity env vars."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)
        monkeypatch.setenv("CLAUDECODE", "1")

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", return_value=mock_result) as mock_run,
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "done"
        env = mock_run.call_args.kwargs["env"]
        assert env["KD_ROLE"] == "peasant"
        assert env["KD_AGENT_NAME"] == session_name
        assert "CLAUDECODE" not in env

    def test_loop_continues_when_done_but_tests_fail(self, project: Path, ticket_path: Path) -> None:
        """Agent says DONE but tests fail — loop should continue, not accept done."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # Agent always says DONE
            result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        test_call_count = 0

        def mock_tests(*args, **kwargs):
            nonlocal test_call_count
            test_call_count += 1
            if test_call_count >= 2:
                return TESTS_PASS
            return TESTS_FAIL

        with (
            patch("kingdom.harness.subprocess.run", side_effect=mock_run),
            patch("kingdom.harness.run_tests", side_effect=mock_tests),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "done"
        assert call_count == 2  # Had to iterate again after test failure

        # Worklog should mention the failure
        ticket = read_ticket(ticket_path)
        assert "pytest failed" in ticket.body.lower()

    def test_loop_continues_when_done_but_lint_fails(self, project: Path, ticket_path: Path) -> None:
        """Agent says DONE but ruff fails — loop should continue."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        lint_call_count = 0

        def mock_lint(*args, **kwargs):
            nonlocal lint_call_count
            lint_call_count += 1
            if lint_call_count >= 2:
                return LINT_PASS
            return LINT_FAIL

        with (
            patch("kingdom.harness.subprocess.run", side_effect=mock_run),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", side_effect=mock_lint),
        ):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "done"
        assert call_count == 2

        # Worklog should mention lint failure
        ticket = read_ticket(ticket_path)
        assert "ruff failed" in ticket.body.lower()

    def test_loop_blocked(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Need help with X.\\n\\nSTATUS: BLOCKED", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.harness.subprocess.run", return_value=mock_result):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "blocked"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "blocked"

    def test_loop_fails_on_backend_error(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Connection refused"
        mock_result.returncode = 1

        with patch("kingdom.harness.subprocess.run", return_value=mock_result):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "failed"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "failed"

    def test_loop_writes_to_thread(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Did some work.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", return_value=mock_result),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        messages = list_messages(project, BRANCH, thread_id)
        peasant_msgs = [m for m in messages if m.from_ == session_name]
        assert len(peasant_msgs) >= 1
        assert "Did some work" in peasant_msgs[0].body

    def test_loop_appends_worklog(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Implemented feature X.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", return_value=mock_result),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        ticket = read_ticket(ticket_path)
        assert "Worklog" in ticket.body
        assert "Implemented feature X" in ticket.body

    def test_loop_updates_session_resume_id(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "new-session-123"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", return_value=mock_result),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        state = get_agent_state(project, BRANCH, session_name)
        assert state.resume_id == "new-session-123"

    def test_loop_continues_across_iterations(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count >= 3:
                result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            else:
                result.stdout = '{"result": "Working on it.\\n\\nSTATUS: CONTINUE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        with (
            patch("kingdom.harness.subprocess.run", side_effect=mock_run),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
        ):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "done"
        assert call_count == 3

    def test_loop_fails_on_unknown_agent(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        status = run_agent_loop(
            base=project,
            branch=BRANCH,
            agent_name="nonexistent-agent",
            ticket_id="kin-test",
            worktree=project,
            thread_id=thread_id,
            session_name=session_name,
        )

        assert status == "failed"

    def test_loop_fails_on_missing_ticket(self, project: Path) -> None:
        thread_id = "missing-ticket-work"
        session_name = "peasant-missing"
        create_thread(project, BRANCH, thread_id, [session_name, "king"], "work")
        set_agent_state(project, BRANCH, session_name, AgentState(name=session_name))

        status = run_agent_loop(
            base=project,
            branch=BRANCH,
            agent_name="claude",
            ticket_id="kin-nonexistent",
            worktree=project,
            thread_id=thread_id,
            session_name=session_name,
        )

        assert status == "failed"

    def test_loop_handles_timeout(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        import subprocess as sp

        with patch("kingdom.harness.subprocess.run", side_effect=sp.TimeoutExpired(cmd="test", timeout=300)):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "failed"

    def test_agent_output_logged(self, project: Path, ticket_path: Path) -> None:
        """Agent stdout/stderr must appear in log records."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Edited foo.py\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = "some debug info from agent"
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", return_value=mock_result),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
            patch("kingdom.harness.logger") as mock_logger,
        ):
            run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        # Collect all info log messages
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        log_text = "\n".join(info_calls)
        assert "Agent stdout" in log_text
        assert "Agent stderr" in log_text
        assert "some debug info from agent" in log_text

    def test_gate_failure_details_logged(self, project: Path, ticket_path: Path) -> None:
        """Full pytest/ruff failure output must appear in log records when gates fail."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        lint_fail_output = "src/foo.py:10:1: F401 `os` imported but unused"
        lint_call_count = 0

        def mock_lint(*args, **kwargs):
            nonlocal lint_call_count
            lint_call_count += 1
            if lint_call_count >= 2:
                return LINT_PASS
            return (False, lint_fail_output)

        with (
            patch("kingdom.harness.subprocess.run", side_effect=mock_run),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", side_effect=mock_lint),
            patch("kingdom.harness.logger") as mock_logger,
        ):
            run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        # Full ruff failure output should appear in a warning log
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        warning_text = "\n".join(warning_calls)
        assert lint_fail_output in warning_text

    def test_loop_stopped_by_signal_after_backend(self, project: Path, ticket_path: Path) -> None:
        """SIGTERM during backend call should stop after it returns."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        import kingdom.harness as harness

        def mock_run_with_signal(*args, **kwargs):
            # Simulate SIGTERM arriving during the backend call
            harness.signal.raise_signal(harness.signal.SIGTERM)
            result = MagicMock()
            result.stdout = '{"result": "Working.\\n\\nSTATUS: CONTINUE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        with patch("kingdom.harness.subprocess.run", side_effect=mock_run_with_signal):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "stopped"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "stopped"

    def test_loop_picks_up_king_messages_sent_while_down(self, project: Path, ticket_path: Path) -> None:
        """King messages posted after peasant's last message should appear as directives."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        # Simulate a previous peasant message (seq 2), then king sends a directive (seq 3)
        add_message(project, BRANCH, thread_id, from_=session_name, to="king", body="Previous work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Please also fix the tests")

        captured_prompts: list[str] = []

        def mock_run(*args, **kwargs):
            # Capture the prompt to verify directives were included
            cmd = args[0] if args else kwargs.get("args", [])
            # The prompt is passed as the last argument
            for item in cmd:
                if "Please also fix the tests" in str(item):
                    captured_prompts.append(str(item))
            result = MagicMock()
            result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        with (
            patch("kingdom.harness.subprocess.run", side_effect=mock_run),
            patch("kingdom.harness.run_tests", return_value=TESTS_PASS),
            patch("kingdom.harness.run_lint", return_value=LINT_PASS),
            patch("kingdom.harness.build_prompt", wraps=build_prompt) as mock_build_prompt,
        ):
            status = run_agent_loop(
                base=project,
                branch=BRANCH,
                agent_name="claude",
                ticket_id="kin-test",
                worktree=project,
                thread_id=thread_id,
                session_name=session_name,
            )

        assert status == "done"
        # The first call to build_prompt should have included the king's directive
        first_call = mock_build_prompt.call_args_list[0]
        directives_arg = first_call[0][2]  # 3rd positional arg is directives
        assert "Please also fix the tests" in directives_arg
