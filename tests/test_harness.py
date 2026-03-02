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
    build_review_prompt,
    check_worktree_branch,
    extract_worklog,
    extract_worklog_entry,
    format_worklog_timestamp,
    get_changed_files,
    get_commit_log,
    get_diff_stat,
    get_new_directives,
    has_code_changes,
    parse_status,
    parse_verdict,
    run_agent_loop,
    run_council_review,
    summarize_feedback,
)
from kingdom.session import AgentState, get_agent_state, set_agent_state
from kingdom.state import ensure_branch_layout, set_current_run
from kingdom.thread import add_message, create_thread, list_messages
from kingdom.ticket import Ticket, read_ticket, write_ticket

BRANCH = "feature/harness-test"

# Common mock return values
COUNCIL_APPROVED = ("approved", [])
COUNCIL_NO_COUNCIL = ("no_council", [])


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
        prompt = build_prompt(
            ticket_path,
            "",
            [],
            1,
            50,
            worktree=Path("/project/.kd/worktrees/kin-001"),
            repo_root=Path("/project"),
            ticket_id="kin-001",
            ticket_title="Fix the thing",
        )
        assert str(ticket_path) in prompt
        assert "/project/.kd/worktrees/kin-001" in prompt
        assert "ticket/kin-001" in prompt
        assert "Fix the thing" in prompt
        assert "iteration 1 of 50" in prompt
        assert "STATUS: DONE" in prompt
        assert "STATUS: BLOCKED" in prompt
        assert "STATUS: CONTINUE" in prompt
        assert "kd tk log kin-001" in prompt
        assert "No headings, no numbered list" in prompt
        # Kingdom context
        assert "Kingdom" in prompt
        assert "council" in prompt
        assert "peasant" in prompt

    def test_prompt_does_not_contain_ticket_body(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50)
        assert "Do the thing" not in prompt
        assert str(ticket_path) in prompt

    def test_prompt_with_worklog(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "- Did step 1", [], 2, 50)
        assert "worklog" in prompt.lower()
        assert "Did step 1" in prompt

    def test_prompt_with_directives(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", ["Focus on tests", "Use pytest"], 3, 50)
        assert "directive" in prompt.lower()
        assert "Focus on tests" in prompt
        assert "Use pytest" in prompt

    def test_prompt_with_all(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(
            ticket_path,
            "- Done A",
            ["Do B"],
            5,
            50,
            worktree=Path("/project/.kd/worktrees/kin-001"),
            repo_root=Path("/project"),
            ticket_id="kin-001",
            ticket_title="Fix the thing",
        )
        assert str(ticket_path) in prompt
        assert "Done A" in prompt
        assert "Do B" in prompt
        assert "iteration 5 of 50" in prompt
        assert "/project" in prompt
        assert "bounced back" in prompt

    def test_prompt_with_phase_prompt(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50, phase_prompt="Always write tests first.")
        assert prompt.startswith("Always write tests first.")
        assert "peasant" in prompt

    def test_prompt_without_phase_prompt(self) -> None:
        ticket_path = Path("/project/tickets/kin-001.md")
        prompt = build_prompt(ticket_path, "", [], 1, 50)
        assert prompt.startswith("You are a peasant")

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
        # Today's entries use [HH:MM] format
        assert re.search(r"\[\d{2}:\d{2}\]", ticket.body)

    def test_entry_from_past_includes_date(self, ticket_path: Path) -> None:
        # To test date-inclusion, we mock datetime.now to return a past date
        # for the entry timestamp (in append_worklog) but "today" for the
        # comparison (in format_worklog_timestamp). We achieve this by returning
        # different values on successive calls.
        yesterday = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)
        today = datetime.now(UTC)
        with patch("kingdom.harness.datetime") as mock_dt:
            # First call: append_worklog gets "yesterday" as the entry time
            # Second call: format_worklog_timestamp gets "today" for comparison
            mock_dt.now.side_effect = [yesterday, today]
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            append_worklog(ticket_path, "Old entry")
        ticket = read_ticket(ticket_path)
        local_yesterday = yesterday.astimezone()
        expected_ts = f"[{local_yesterday.strftime('%Y-%m-%d %H:%M')}]"
        assert expected_ts in ticket.body

    def test_appends_to_end_of_document(self, ticket_path: Path) -> None:
        """Worklog entries append to end of document (worklog is always last section)."""
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- Existing"
        write_ticket(ticket, ticket_path)

        append_worklog(ticket_path, "New entry")
        ticket = read_ticket(ticket_path)

        # New entry should be at the very end
        assert ticket.body.rstrip().endswith("New entry")


class TestFormatWorklogTimestamp:
    def test_today_shows_time_only(self) -> None:
        now = datetime.now(UTC)
        local_now = now.astimezone()
        result = format_worklog_timestamp(now)
        assert result == f"[{local_now.strftime('%H:%M')}]"
        # Should NOT contain a date
        assert "-" not in result

    def test_yesterday_shows_date_and_time(self) -> None:
        from datetime import timedelta

        yesterday = datetime.now(UTC) - timedelta(days=1)
        local_yesterday = yesterday.astimezone()
        result = format_worklog_timestamp(yesterday)
        expected = f"[{local_yesterday.strftime('%Y-%m-%d %H:%M')}]"
        assert result == expected

    def test_old_date_shows_date_and_time(self) -> None:
        old = datetime(2024, 1, 15, 14, 30, tzinfo=UTC)
        local_old = old.astimezone()
        result = format_worklog_timestamp(old)
        expected = f"[{local_old.strftime('%Y-%m-%d %H:%M')}]"
        assert result == expected

    def test_format_consistency(self) -> None:
        """Today entries use [HH:MM], older entries use [YYYY-MM-DD HH:MM]."""
        now = datetime.now(UTC)
        today_result = format_worklog_timestamp(now)
        assert re.match(r"^\[\d{2}:\d{2}\]$", today_result)

        old = datetime(2020, 3, 5, 8, 5, tzinfo=UTC)
        old_result = format_worklog_timestamp(old)
        assert re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]$", old_result)


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

    def test_returns_entries_from_worklog_section(self, ticket_path: Path) -> None:
        """Extracts entries from the Worklog section."""
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- Entry 1\n- Entry 2"
        write_ticket(ticket, ticket_path)

        worklog = extract_worklog(ticket_path)
        assert "Entry 1" in worklog
        assert "Entry 2" in worklog

    def test_stops_at_next_heading(self, ticket_path: Path) -> None:
        """extract_worklog should not include content from sections after Worklog."""
        ticket = read_ticket(ticket_path)
        ticket.body += "\n\n## Worklog\n\n- Entry 1\n\n## Notes\n\nThis is not worklog."
        write_ticket(ticket, ticket_path)

        worklog = extract_worklog(ticket_path)
        assert "Entry 1" in worklog
        assert "Notes" not in worklog
        assert "not worklog" not in worklog


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

    def test_loop_writes_iteration_start_to_worklog(self, project: Path, ticket_path: Path) -> None:
        """Each iteration appends a 'calling agent' entry to the worklog."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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
        assert "Iteration 1/" in ticket.body
        assert "calling agent" in ticket.body

    def test_loop_done_when_gates_pass(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        assert status == "needs_king_review"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "needs_king_review"

    def test_loop_allows_done_without_changes(self, project: Path, ticket_path: Path) -> None:
        """Agent says DONE with no code changes — should proceed to council review."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        agent_call_count = 0

        def mock_agent(cmd, **kwargs):
            nonlocal agent_call_count
            agent_call_count += 1
            result = MagicMock()
            result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        with (
            patch("kingdom.harness.run_streaming_subprocess", side_effect=mock_agent),
            patch("kingdom.harness.has_code_changes", return_value=False),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        assert status == "needs_king_review"
        assert agent_call_count == 1  # DONE accepted on first try

        # Worklog should note the no-changes situation
        ticket = read_ticket(ticket_path)
        assert "no code changes" in ticket.body.lower()

    def test_loop_passes_peasant_identity_env(self, project: Path, ticket_path: Path, monkeypatch) -> None:
        """Backend subprocess should receive peasant identity and KD_BASE env vars."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)
        monkeypatch.setenv("CLAUDECODE", "1")

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result) as mock_stream,
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        assert status == "needs_king_review"
        env = mock_stream.call_args.kwargs["env"]
        assert env["KD_ROLE"] == "peasant"
        assert env["KD_AGENT_NAME"] == session_name
        assert env["KD_BASE"] == str(project)
        assert "CLAUDECODE" not in env

    def test_loop_blocked(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Need help with X.\\n\\nSTATUS: BLOCKED", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result):
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

        with patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result):
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
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        agent_call_count = 0

        def mock_agent(cmd, **kwargs):
            nonlocal agent_call_count
            agent_call_count += 1
            result = MagicMock()
            if agent_call_count >= 3:
                result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            else:
                result.stdout = '{"result": "Working on it.\\n\\nSTATUS: CONTINUE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        with (
            patch("kingdom.harness.run_streaming_subprocess", side_effect=mock_agent),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
            patch("kingdom.harness.has_code_changes", return_value=True),
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

        assert status == "needs_king_review"
        assert agent_call_count == 3

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

        with patch("kingdom.harness.run_streaming_subprocess", side_effect=sp.TimeoutExpired(cmd="test", timeout=300)):
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
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        with patch("kingdom.harness.run_streaming_subprocess", side_effect=mock_run_with_signal):
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

    def test_loop_records_start_sha(self, project: Path, ticket_path: Path) -> None:
        """Harness should record start_sha on first run."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        def mock_git(cmd, **kwargs):
            result = MagicMock()
            if cmd and "rev-parse" in cmd:
                if "--abbrev-ref" in cmd:
                    result.stdout = "ticket/kin-test\n"
                else:
                    result.stdout = "abc123def456\n"
                result.returncode = 0
            else:
                result.stdout = ""
                result.returncode = 0
            result.stderr = ""
            return result

        mock_agent_result = MagicMock()
        mock_agent_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_agent_result.stderr = ""
        mock_agent_result.returncode = 0

        with (
            patch("kingdom.harness.subprocess.run", side_effect=mock_git),
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_agent_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
            patch("kingdom.harness.has_code_changes", return_value=True),
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

        assert status == "needs_king_review"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.start_sha == "abc123def456"

    def test_loop_does_not_overwrite_existing_start_sha(self, project: Path, ticket_path: Path) -> None:
        """If start_sha is already set, harness should not overwrite it."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)
        # Pre-set start_sha
        from kingdom.session import update_agent_state as update_state

        update_state(project, BRANCH, session_name, start_sha="original-sha")

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
            patch("kingdom.harness.has_code_changes", return_value=True),
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

        assert status == "needs_king_review"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.start_sha == "original-sha"

    def test_loop_picks_up_king_messages_sent_while_down(self, project: Path, ticket_path: Path) -> None:
        """King messages posted after peasant's last message should appear as directives."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        # Simulate a previous peasant message (seq 2), then king sends a directive (seq 3)
        add_message(project, BRANCH, thread_id, from_=session_name, to="king", body="Previous work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Please also fix the tests")

        mock_agent_result = MagicMock()
        mock_agent_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_agent_result.stderr = ""
        mock_agent_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_agent_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        assert status == "needs_king_review"
        # The first call to build_prompt should have included the king's directive
        first_call = mock_build_prompt.call_args_list[0]
        directives_arg = first_call[0][2]  # 3rd positional arg is directives
        assert "Please also fix the tests" in directives_arg


class TestParseVerdict:
    def test_approved(self) -> None:
        assert parse_verdict("Looks good.\n\nVERDICT: APPROVED") == "approved"

    def test_blocking(self) -> None:
        assert parse_verdict("Bug found.\n\nVERDICT: BLOCKING") == "blocking"

    def test_case_insensitive(self) -> None:
        assert parse_verdict("VERDICT: approved") == "approved"
        assert parse_verdict("VERDICT: Blocking") == "blocking"

    def test_missing_verdict_returns_unknown(self) -> None:
        assert parse_verdict("Just some review text without verdict") == "unknown"

    def test_empty_string(self) -> None:
        assert parse_verdict("") == "unknown"

    def test_verdict_in_middle_ignored(self) -> None:
        """Only the last VERDICT line counts."""
        text = "VERDICT: BLOCKING\nMore discussion\nVERDICT: APPROVED"
        assert parse_verdict(text) == "approved"

    def test_bold_markdown(self) -> None:
        assert parse_verdict("Review.\n\n**VERDICT: APPROVED**") == "approved"
        assert parse_verdict("Review.\n\n**VERDICT: BLOCKING**") == "blocking"

    def test_italic_and_backtick(self) -> None:
        assert parse_verdict("_VERDICT: APPROVED_") == "approved"
        assert parse_verdict("`VERDICT: BLOCKING`") == "blocking"

    def test_blockquote(self) -> None:
        assert parse_verdict("> VERDICT: APPROVED") == "approved"

    def test_list_item(self) -> None:
        assert parse_verdict("- VERDICT: BLOCKING") == "blocking"

    def test_heading(self) -> None:
        assert parse_verdict("## VERDICT: APPROVED") == "approved"


class TestBuildReviewPrompt:
    def test_includes_ticket_info(self) -> None:
        prompt = build_review_prompt(
            changed_files="foo.py | 2 +-",
            ticket_title="Fix bug",
            ticket_body="A bug in module X.",
        )
        assert "Fix bug" in prompt
        assert "A bug in module X" in prompt
        assert "foo.py" in prompt

    def test_includes_changed_files_not_full_diff(self) -> None:
        prompt = build_review_prompt(changed_files="foo.py | 2 +-\nbar.py | 1 +")
        assert "foo.py" in prompt
        assert "bar.py" in prompt
        # Should NOT contain a diff code block — we point reviewers at the code
        assert "```diff" not in prompt

    def test_includes_worklog(self) -> None:
        prompt = build_review_prompt(
            changed_files="foo.py | 1 +",
            ticket_title="Title",
            ticket_body="Body",
            worklog="- Fixed the tests\n- Added validation",
        )
        assert "Fixed the tests" in prompt
        assert "Added validation" in prompt

    def test_excludes_worklog_from_body(self) -> None:
        body = "Description here.\n\n## Worklog\n\n- [12:00] Did stuff"
        prompt = build_review_prompt(
            changed_files="foo.py | 1 +",
            ticket_title="Title",
            ticket_body=body,
        )
        # The ticket description section should NOT include the worklog
        assert "Did stuff" not in prompt.split("### Changed Files")[0]

    def test_verdict_instructions(self) -> None:
        prompt = build_review_prompt(changed_files="foo.py | 1 +")
        assert "VERDICT: APPROVED" in prompt
        assert "VERDICT: BLOCKING" in prompt

    def test_includes_review_commands(self) -> None:
        prompt = build_review_prompt(
            changed_files="foo.py | 1 +",
            base_branch="origin/master",
        )
        assert "git diff origin/master...HEAD" in prompt
        assert "git log" in prompt

    def test_works_without_ticket(self) -> None:
        prompt = build_review_prompt(
            changed_files="foo.py | 1 +",
            base_branch="origin/master",
            branch="feature/x",
            commits="abc123 Fix bug",
        )
        assert "foo.py" in prompt
        assert "feature/x" in prompt
        assert "Fix bug" in prompt
        assert "VERDICT:" in prompt

    def test_includes_ticket_path(self) -> None:
        prompt = build_review_prompt(
            changed_files="foo.py | 1 +",
            ticket_title="Fix bug",
            ticket_body="Body",
            ticket_path=".kd/branches/main/tickets/1234.md",
        )
        assert ".kd/branches/main/tickets/1234.md" in prompt


class TestHasCodeChanges:
    def test_detects_uncommitted_changes(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=" M src/foo.py\n")
            assert has_code_changes(tmp_path, "abc123") is True

    def test_detects_committed_changes(self, tmp_path: Path) -> None:
        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if "status" in cmd:
                result.stdout = ""  # No uncommitted changes
            else:
                result.stdout = "abc456 Add feature\n"  # Committed changes
            return result

        with patch("kingdom.harness.subprocess.run", side_effect=mock_run):
            assert has_code_changes(tmp_path, "abc123") is True

    def test_no_changes(self, tmp_path: Path) -> None:
        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        with patch("kingdom.harness.subprocess.run", side_effect=mock_run):
            assert has_code_changes(tmp_path, "abc123") is False

    def test_no_start_sha_no_uncommitted_assumes_changes(self, tmp_path: Path) -> None:
        """When start_sha is None and working tree is clean, assume changes exist.

        We can't determine whether committed changes exist without a baseline,
        so the safe default is True (avoid rejecting valid work).
        """
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            assert has_code_changes(tmp_path, None) is True

    def test_returns_true_on_error(self, tmp_path: Path) -> None:
        """On git failure, assume changes exist to avoid false rejections."""
        with patch("kingdom.harness.subprocess.run", side_effect=FileNotFoundError):
            assert has_code_changes(tmp_path, "abc123") is True


class TestGetChangedFiles:
    def test_with_start_sha(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=" foo.py | 2 +-\n 1 file changed")
            result = get_changed_files(tmp_path, "abc123")
            mock_run.assert_called_once()
            assert "--stat" in mock_run.call_args[0][0]
            assert "abc123..HEAD" in mock_run.call_args[0][0]
            assert "foo.py" in result

    def test_without_start_sha(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=" bar.py | 1 -\n 1 file changed")
            result = get_changed_files(tmp_path, None)
            assert "--stat" in mock_run.call_args[0][0]
            assert "HEAD" in mock_run.call_args[0][0]
            assert "bar.py" in result

    def test_empty_output(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = get_changed_files(tmp_path, "abc123")
            assert result == "(no changes detected)"

    def test_handles_timeout(self, tmp_path: Path) -> None:
        import subprocess as sp

        with patch("kingdom.harness.subprocess.run", side_effect=sp.TimeoutExpired("git", 30)):
            result = get_changed_files(tmp_path, "abc123")
            assert result == "(could not generate file list)"

    def test_feature_branch_uses_three_dot(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=" foo.py | 2 +-")
            get_changed_files(tmp_path, None, feature_branch="feature/x")
            assert "feature/x...HEAD" in mock_run.call_args[0][0]


class TestGetCommitLog:
    def test_with_feature_branch(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123 Fix bug\ndef456 Add feature")
            result = get_commit_log(tmp_path, None, feature_branch="main")
            assert "main..HEAD" in mock_run.call_args[0][0]
            assert "Fix bug" in result

    def test_with_start_sha(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123 Fix bug")
            result = get_commit_log(tmp_path, "abc123")
            assert "abc123..HEAD" in mock_run.call_args[0][0]
            assert "Fix bug" in result

    def test_empty_log(self, tmp_path: Path) -> None:
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = get_commit_log(tmp_path, "abc123")
            assert result == ""


class TestRunCouncilReview:
    def test_no_council_members(self, project: Path, ticket_path: Path) -> None:
        """With no council configured, should return no_council."""
        mock_council = MagicMock()
        mock_council.members = []

        with patch("kingdom.council.council.Council.create", return_value=mock_council):
            outcome, feedback = run_council_review(
                base=project,
                branch=BRANCH,
                worktree=project,
                ticket_path=ticket_path,
                session_name="peasant-test",
                thread_id="test-thread",
                start_sha=None,
                council_timeout=600,
            )

        assert outcome == "no_council"
        assert feedback == []

    def test_all_approved(self, project: Path, ticket_path: Path) -> None:
        """All council members approve — should return approved."""
        from kingdom.council.base import AgentResponse

        thread_id = "review-thread"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex"], "council")

        mock_council = MagicMock()
        mock_council.members = [MagicMock(name="claude"), MagicMock(name="codex")]
        mock_council.query_to_thread.return_value = {
            "claude": AgentResponse(name="claude", text="Looks great!\n\nVERDICT: APPROVED"),
            "codex": AgentResponse(name="codex", text="All good.\n\nVERDICT: APPROVED"),
        }

        with patch("kingdom.council.council.Council.create", return_value=mock_council):
            outcome, feedback = run_council_review(
                base=project,
                branch=BRANCH,
                worktree=project,
                ticket_path=ticket_path,
                session_name="peasant-test",
                thread_id=thread_id,
                start_sha="abc123",
                council_timeout=600,
            )

        assert outcome == "approved"
        # Approval now preserves member feedback
        assert len(feedback) == 2
        assert any("claude" in f for f in feedback)
        assert any("codex" in f for f in feedback)

    def test_one_blocking(self, project: Path, ticket_path: Path) -> None:
        """One councillor blocks — should return blocking with feedback."""
        from kingdom.council.base import AgentResponse

        thread_id = "review-thread2"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex"], "council")

        mock_council = MagicMock()
        mock_council.members = [MagicMock(name="claude"), MagicMock(name="codex")]
        mock_council.query_to_thread.return_value = {
            "claude": AgentResponse(name="claude", text="Looks fine.\n\nVERDICT: APPROVED"),
            "codex": AgentResponse(name="codex", text="Missing tests.\n\nVERDICT: BLOCKING"),
        }

        with patch("kingdom.council.council.Council.create", return_value=mock_council):
            outcome, feedback = run_council_review(
                base=project,
                branch=BRANCH,
                worktree=project,
                ticket_path=ticket_path,
                session_name="peasant-test",
                thread_id=thread_id,
                start_sha="abc123",
                council_timeout=600,
            )

        assert outcome == "blocking"
        # Blocking reviews now return ALL members' feedback, not just blockers
        assert len(feedback) == 2
        assert any("claude" in f for f in feedback)
        assert any("codex" in f for f in feedback)
        assert any("Missing tests" in f for f in feedback)

    def test_error_response_skipped(self, project: Path, ticket_path: Path) -> None:
        """Errored council responses should be skipped, not block."""
        from kingdom.council.base import AgentResponse

        thread_id = "review-thread3"
        create_thread(project, BRANCH, thread_id, ["king", "claude"], "council")

        mock_council = MagicMock()
        mock_council.members = [MagicMock(name="claude")]
        mock_council.query_to_thread.return_value = {
            "claude": AgentResponse(name="claude", text="", error="Connection failed"),
        }

        with patch("kingdom.council.council.Council.create", return_value=mock_council):
            outcome, feedback = run_council_review(
                base=project,
                branch=BRANCH,
                worktree=project,
                ticket_path=ticket_path,
                session_name="peasant-test",
                thread_id=thread_id,
                start_sha=None,
                council_timeout=600,
            )

        assert outcome == "approved"
        assert feedback == []


class TestSummarizeFeedback:
    """Tests for summarize_feedback helper."""

    def test_empty_feedback(self) -> None:
        assert summarize_feedback([]) == ""

    def test_single_member_approved(self) -> None:
        feedback = ["[claude] Looks great! Clean implementation.\n\nVERDICT: APPROVED"]
        result = summarize_feedback(feedback)
        assert result == "[claude] APPROVED: Looks great! Clean implementation."

    def test_multiple_members(self) -> None:
        feedback = [
            "[claude] Well done.\n\nVERDICT: APPROVED",
            "[codex] Missing edge case.\n\nVERDICT: BLOCKING",
        ]
        result = summarize_feedback(feedback)
        assert "[claude] APPROVED: Well done." in result
        assert "[codex] BLOCKING: Missing edge case." in result

    def test_truncates_long_text(self) -> None:
        long_text = "A" * 200
        feedback = [f"[claude] {long_text}\n\nVERDICT: APPROVED"]
        result = summarize_feedback(feedback, max_chars=50)
        assert len(result.split("] ", 1)[1]) <= 50
        assert result.endswith("...")

    def test_skips_empty_lines(self) -> None:
        feedback = ["[claude] \n\nActual content here.\n\nVERDICT: APPROVED"]
        result = summarize_feedback(feedback)
        assert "Actual content here." in result

    def test_no_bracket_prefix(self) -> None:
        feedback = ["Just some feedback text\n\nVERDICT: APPROVED"]
        result = summarize_feedback(feedback)
        assert result == "APPROVED: Just some feedback text"

    def test_missing_verdict_shows_unknown(self) -> None:
        feedback = ["[claude] Some review text without a verdict line"]
        result = summarize_feedback(feedback)
        assert "[claude] UNKNOWN: Some review text without a verdict line" in result


class TestGetDiffStat:
    """Tests for get_diff_stat helper."""

    def test_returns_none_on_error(self, tmp_path: Path) -> None:
        """Non-git directory returns None."""
        assert get_diff_stat(tmp_path) is None

    def test_returns_none_when_no_changes(self, tmp_path: Path) -> None:
        with patch(
            "kingdom.harness.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=""),
        ):
            assert get_diff_stat(tmp_path) is None

    def test_returns_stat_output(self, tmp_path: Path) -> None:
        stat_output = " src/foo.py | 5 ++---\n 1 file changed, 2 insertions(+), 3 deletions(-)"
        with patch(
            "kingdom.harness.subprocess.run",
            return_value=MagicMock(returncode=0, stdout=stat_output),
        ):
            result = get_diff_stat(tmp_path)
            assert result is not None
            assert "foo.py" in result

    def test_handles_timeout(self, tmp_path: Path) -> None:
        import subprocess as sp

        with patch("kingdom.harness.subprocess.run", side_effect=sp.TimeoutExpired("git", 10)):
            assert get_diff_stat(tmp_path) is None


class TestCouncilReviewInLoop:
    """Integration tests for council review within the harness loop."""

    def setup_for_loop(self, project: Path, ticket_path: Path) -> tuple[str, str]:
        thread_id = "kin-test-work"
        session_name = "peasant-kin-test"
        create_thread(project, BRANCH, thread_id, [session_name, "king"], "work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Start work")
        set_agent_state(project, BRANCH, session_name, AgentState(name=session_name))
        return thread_id, session_name

    def test_council_approved_sets_needs_king_review(self, project: Path, ticket_path: Path) -> None:
        """When council approves, status should be needs_king_review and ticket in_review."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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

        assert status == "needs_king_review"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "needs_king_review"

        # Ticket should be in_review
        ticket = read_ticket(ticket_path)
        assert ticket.status == "in_review"

    def test_council_blocking_bounces_back(self, project: Path, ticket_path: Path) -> None:
        """When council blocks, peasant should return to working and then complete."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        agent_call_count = 0

        def mock_agent(cmd, **kwargs):
            nonlocal agent_call_count
            agent_call_count += 1
            result = MagicMock()
            result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
            result.stderr = ""
            result.returncode = 0
            return result

        review_call_count = 0

        def mock_review(**kwargs):
            nonlocal review_call_count
            review_call_count += 1
            if review_call_count == 1:
                return ("blocking", ["[codex] Missing edge case tests.\n\nVERDICT: BLOCKING"])
            return ("approved", [])

        with (
            patch("kingdom.harness.run_streaming_subprocess", side_effect=mock_agent),
            patch("kingdom.harness.run_council_review", side_effect=mock_review),
            patch("kingdom.harness.add_message", wraps=add_message) as mock_add_message,
            patch("kingdom.harness.has_code_changes", return_value=True),
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

        assert status == "needs_king_review"
        assert agent_call_count == 2  # One initial, one after bounce
        assert review_call_count == 2  # One blocking, one approved

        # Bounce count should be 1
        state = get_agent_state(project, BRANCH, session_name)
        assert state.review_bounce_count == 1

        # Council feedback message should have been written to the thread
        feedback_calls = [
            call for call in mock_add_message.call_args_list if "Council Review Feedback (BLOCKING)" in str(call)
        ]
        assert len(feedback_calls) == 1, f"Expected 1 council feedback message, got {len(feedback_calls)}"

    def test_bounce_limit_escalates(self, project: Path, ticket_path: Path) -> None:
        """After 3 bounces, should escalate to king even if still blocking."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_agent_result = MagicMock()
        mock_agent_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_agent_result.stderr = ""
        mock_agent_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_agent_result),
            patch(
                "kingdom.harness.run_council_review",
                return_value=("blocking", ["[codex] Still failing.\n\nVERDICT: BLOCKING"]),
            ),
            patch("kingdom.harness.add_message", wraps=add_message) as mock_add_message,
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

        assert status == "needs_king_review"
        state = get_agent_state(project, BRANCH, session_name)
        assert state.review_bounce_count == 3

        # Worklog should mention escalation
        ticket = read_ticket(ticket_path)
        assert "escalating" in ticket.body.lower()

        # Council feedback written on bounces 1 and 2; bounce 3 hits limit and escalates without writing
        feedback_calls = [
            call for call in mock_add_message.call_args_list if "Council Review Feedback (BLOCKING)" in str(call)
        ]
        assert len(feedback_calls) == 2, f"Expected 2 council feedback messages, got {len(feedback_calls)}"

    def test_council_feedback_filenotfound_continues(self, project: Path, ticket_path: Path) -> None:
        """When add_message raises FileNotFoundError, bounce loop should continue gracefully."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        review_call_count = 0

        def mock_review(**kwargs):
            nonlocal review_call_count
            review_call_count += 1
            if review_call_count == 1:
                return ("blocking", ["[codex] Bug found.\n\nVERDICT: BLOCKING"])
            return ("approved", [])

        mock_agent_result = MagicMock()
        mock_agent_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_agent_result.stderr = ""
        mock_agent_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_agent_result),
            patch("kingdom.harness.run_council_review", side_effect=mock_review),
            patch("kingdom.harness.add_message", side_effect=FileNotFoundError("thread gone")),
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

        # Should still complete despite feedback write failure
        assert status == "needs_king_review"
        assert review_call_count == 2  # Bounced once, then approved

    def test_no_council_skips_review(self, project: Path, ticket_path: Path) -> None:
        """When no council is configured, should go straight to needs_king_review."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_NO_COUNCIL),
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

        assert status == "needs_king_review"
        ticket = read_ticket(ticket_path)
        assert "no council" in ticket.body.lower()

    def test_council_timeout_escalates(self, project: Path, ticket_path: Path) -> None:
        """When council times out, should escalate to king."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=("timeout", [])),
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

        assert status == "needs_king_review"
        ticket = read_ticket(ticket_path)
        assert "timed out" in ticket.body.lower()

    def test_ticket_status_transitions(self, project: Path, ticket_path: Path) -> None:
        """Ticket should transition open -> in_review during council review."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        # Mark ticket in_progress (as peasant start would)
        ticket = read_ticket(ticket_path)
        ticket.status = "in_progress"
        write_ticket(ticket, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        statuses_seen = []

        def mock_review(**kwargs):
            # Capture ticket status at the time council review runs
            t = read_ticket(ticket_path)
            statuses_seen.append(t.status)
            return ("approved", [])

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", side_effect=mock_review),
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

        # During council review, ticket should have been in_review
        assert statuses_seen == ["in_review"]


class TestGetDiffStatWithSince:
    """Tests for get_diff_stat with the since parameter (committed changes)."""

    def test_since_param_diffs_against_sha(self, tmp_path: Path) -> None:
        """When since is provided, should run git diff --stat since..HEAD."""
        stat_output = " src/foo.py | 3 ++-\n 1 file changed"
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=stat_output)
            result = get_diff_stat(tmp_path, since="abc123")
            assert result is not None
            assert "foo.py" in result
            # First call should use since..HEAD
            cmd = mock_run.call_args_list[0][0][0]
            assert "abc123..HEAD" in cmd

    def test_since_empty_falls_back_to_uncommitted(self, tmp_path: Path) -> None:
        """When since diff is empty, falls back to uncommitted changes."""
        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.returncode = 0
            if call_count == 1:
                result.stdout = ""  # No committed changes since SHA
            else:
                result.stdout = " src/bar.py | 1 +\n 1 file changed"
            return result

        with patch("kingdom.harness.subprocess.run", side_effect=mock_run):
            result = get_diff_stat(tmp_path, since="abc123")
            assert result is not None
            assert "bar.py" in result
            assert call_count == 2

    def test_without_since_uses_head(self, tmp_path: Path) -> None:
        """Without since, should diff against HEAD (original behavior)."""
        stat_output = " src/foo.py | 2 +-\n 1 file changed"
        with patch("kingdom.harness.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=stat_output)
            result = get_diff_stat(tmp_path)
            assert result is not None
            cmd = mock_run.call_args_list[0][0][0]
            assert cmd == ["git", "diff", "--stat", "HEAD"]


class TestExtractWorklogEntryHeadings:
    """Tests for extract_worklog_entry skipping bare markdown headings."""

    def test_skips_bare_heading(self) -> None:
        text = "## What I did this iteration\n\nImplemented the auth module.\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert entry == "Implemented the auth module."

    def test_skips_multiple_headings(self) -> None:
        text = "## Summary\n\n## Details\n\nFixed the parsing bug.\n\nSTATUS: CONTINUE"
        entry = extract_worklog_entry(text)
        assert entry == "Fixed the parsing bug."

    def test_heading_with_content_below_on_same_para(self) -> None:
        """A heading followed by content in the same paragraph is kept."""
        text = "## Summary\nActual details here.\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert "Summary" in entry
        assert "Actual details" in entry

    def test_no_heading_still_works(self) -> None:
        text = "I fixed the bug.\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert entry == "I fixed the bug."

    def test_only_heading_returns_empty(self) -> None:
        text = "## What I did\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert entry == ""

    def test_skips_numbered_placeholder_heading(self) -> None:
        text = "1. What I did this iteration\n\nImplemented the auth module.\n\nSTATUS: DONE"
        entry = extract_worklog_entry(text)
        assert entry == "Implemented the auth module."


class TestFirstIterationContext:
    """Tests for first iteration worklog entry including ticket context."""

    def setup_for_loop(self, project: Path, ticket_path: Path) -> tuple[str, str]:
        thread_id = "kin-test-work"
        session_name = "peasant-kin-test"
        create_thread(project, BRANCH, thread_id, [session_name, "king"], "work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Start work")
        set_agent_state(project, BRANCH, session_name, AgentState(name=session_name))
        return thread_id, session_name

    def test_first_iteration_includes_ticket_title(self, project: Path, ticket_path: Path) -> None:
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "All done.\\n\\nSTATUS: DONE", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
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
        assert "Test ticket" in ticket.body


class TestAgentResultFallbackSummary:
    """Tests for fallback agent-result summaries when extraction is empty."""

    def setup_for_loop(self, project: Path, ticket_path: Path) -> tuple[str, str]:
        thread_id = "kin-test-work"
        session_name = "peasant-kin-test"
        create_thread(project, BRANCH, thread_id, [session_name, "king"], "work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Start work")
        set_agent_state(project, BRANCH, session_name, AgentState(name=session_name))
        return thread_id, session_name

    def test_empty_agent_summary_shows_diff_stat_only(self, project: Path, ticket_path: Path) -> None:
        """When agent writes only a placeholder heading, the diff stat entry still appears."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        backend_result = MagicMock()
        backend_result.stdout = '{"result": "1. What I did this iteration\\n\\nSTATUS: DONE", "session_id": "s1"}'
        backend_result.stderr = ""
        backend_result.returncode = 0

        with (
            patch("kingdom.harness.run_streaming_subprocess", return_value=backend_result),
            patch(
                "kingdom.harness.get_diff_stat",
                return_value=" src/kingdom/harness.py | 2 +-\n 1 file changed",
            ),
            patch("kingdom.harness.run_council_review", return_value=COUNCIL_APPROVED),
            patch("kingdom.harness.has_code_changes", return_value=True),
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
        # No redundant "Updated 1 file" fallback — just the diff stat entry
        assert "Updated 1 file: src/kingdom/harness.py" not in ticket.body
        assert "Files changed:" in ticket.body


class TestBlockingReviewAllFeedback:
    """Tests for blocking reviews including all members' verdicts."""

    def test_blocking_review_includes_approving_member(self, project: Path, ticket_path: Path) -> None:
        """When one member blocks, feedback should include approving members too."""
        from kingdom.council.base import AgentResponse

        thread_id = "review-all-feedback"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex"], "council")

        mock_council = MagicMock()
        mock_council.members = [MagicMock(name="claude"), MagicMock(name="codex")]
        mock_council.query_to_thread.return_value = {
            "claude": AgentResponse(name="claude", text="Looks fine.\n\nVERDICT: APPROVED"),
            "codex": AgentResponse(name="codex", text="Missing tests.\n\nVERDICT: BLOCKING"),
        }

        with patch("kingdom.council.council.Council.create", return_value=mock_council):
            outcome, feedback = run_council_review(
                base=project,
                branch=BRANCH,
                worktree=project,
                ticket_path=ticket_path,
                session_name="peasant-test",
                thread_id=thread_id,
                start_sha="abc123",
                council_timeout=600,
            )

        assert outcome == "blocking"
        assert len(feedback) == 2
        # Both members' feedback should be present
        names_in_feedback = [f.split("]")[0] for f in feedback]
        assert any("claude" in n for n in names_in_feedback)
        assert any("codex" in n for n in names_in_feedback)


class TestCleanAgentEnvKdBase:
    """Tests for KD_BASE injection in clean_agent_env."""

    def test_kd_base_injected(self, monkeypatch) -> None:
        from kingdom.agent import clean_agent_env

        monkeypatch.delenv("KD_BASE", raising=False)
        env = clean_agent_env(kd_base="/tmp/project")
        assert env["KD_BASE"] == "/tmp/project"

    def test_kd_base_not_set_when_none(self, monkeypatch) -> None:
        from kingdom.agent import clean_agent_env

        monkeypatch.delenv("KD_BASE", raising=False)
        env = clean_agent_env()
        assert "KD_BASE" not in env

    def test_all_env_vars_together(self, monkeypatch) -> None:
        from kingdom.agent import clean_agent_env

        monkeypatch.setenv("CLAUDECODE", "1")
        env = clean_agent_env(role="peasant", agent_name="test-agent", kd_base="/project")
        assert env["KD_ROLE"] == "peasant"
        assert env["KD_AGENT_NAME"] == "test-agent"
        assert env["KD_BASE"] == "/project"
        assert "CLAUDECODE" not in env


class TestRunStreamingSubprocess:
    """Tests for run_streaming_subprocess."""

    def test_captures_stdout_and_stderr(self, tmp_path: Path) -> None:
        from kingdom.harness import run_streaming_subprocess

        result = run_streaming_subprocess(
            ["echo", "hello world"],
            cwd=tmp_path,
            env={},
            timeout=10,
        )
        assert result.returncode == 0
        assert "hello world" in result.stdout

    def test_writes_to_live_log(self, tmp_path: Path) -> None:
        from kingdom.harness import run_streaming_subprocess

        log_path = tmp_path / "logs" / "live.log"
        result = run_streaming_subprocess(
            ["echo", "streamed output"],
            cwd=tmp_path,
            env={},
            timeout=10,
            live_log_path=log_path,
        )
        assert result.returncode == 0
        assert log_path.exists()
        log_content = log_path.read_text()
        assert "streamed output" in log_content

    def test_timeout_raises(self, tmp_path: Path) -> None:
        import subprocess as sp

        from kingdom.harness import run_streaming_subprocess

        with pytest.raises(sp.TimeoutExpired):
            run_streaming_subprocess(
                ["sleep", "60"],
                cwd=tmp_path,
                env={},
                timeout=1,
            )

    def test_accumulates_full_output(self, tmp_path: Path) -> None:
        """Full stdout must be accumulated for parse_response compatibility."""
        import sys

        from kingdom.harness import run_streaming_subprocess

        result = run_streaming_subprocess(
            [sys.executable, "-c", "for i in range(5): print(f'line {i}')"],
            cwd=tmp_path,
            env={},
            timeout=10,
        )
        assert result.returncode == 0
        for i in range(5):
            assert f"line {i}" in result.stdout


class TestCheckWorktreeBranch:
    """Tests for check_worktree_branch — the branch escape tripwire."""

    def test_matching_branch_returns_true(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ticket/kin-042\n"
        with patch("kingdom.harness.subprocess.run", return_value=mock_result):
            assert check_worktree_branch(Path("/fake"), "ticket/kin-042") is True

    def test_wrong_branch_returns_false(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "code-cleanup\n"
        with patch("kingdom.harness.subprocess.run", return_value=mock_result):
            assert check_worktree_branch(Path("/fake"), "ticket/kin-042") is False

    def test_git_failure_returns_true(self) -> None:
        """Git errors should not block the agent — return True (pass)."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("kingdom.harness.subprocess.run", return_value=mock_result):
            assert check_worktree_branch(Path("/fake"), "ticket/kin-042") is True

    def test_git_timeout_returns_true(self) -> None:
        """Timeouts should not block the agent — return True (pass)."""
        import subprocess

        with patch("kingdom.harness.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            assert check_worktree_branch(Path("/fake"), "ticket/kin-042") is True

    def test_hand_mode_feature_branch(self) -> None:
        """In hand mode, expected branch is the feature branch, not ticket/."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "feature/my-feature\n"
        with patch("kingdom.harness.subprocess.run", return_value=mock_result):
            assert check_worktree_branch(Path("/fake"), "feature/my-feature") is True


class TestBranchEscapeInLoop:
    """Integration tests: branch escape detection in run_agent_loop."""

    def setup_for_loop(self, project: Path, ticket_path: Path) -> tuple[str, str]:
        """Set up thread and session for a loop test. Returns (thread_id, session_name)."""
        thread_id = "kin-test-work"
        session_name = "peasant-kin-test"
        create_thread(project, BRANCH, thread_id, [session_name, "king"], "work")
        add_message(project, BRANCH, thread_id, from_="king", to=session_name, body="Start work")
        set_agent_state(project, BRANCH, session_name, AgentState(name=session_name))
        return thread_id, session_name

    def test_pre_loop_escape_aborts(self, project: Path, ticket_path: Path) -> None:
        """If worktree is already on the wrong branch, abort before calling the agent."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        with patch("kingdom.harness.check_worktree_branch", return_value=False):
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
        ticket = read_ticket(ticket_path)
        assert "BRANCH ESCAPE" in ticket.body

        # Verify session state is updated to "failed" (not stuck in "working")
        from kingdom.session import get_agent_state

        state = get_agent_state(project, BRANCH, session_name)
        assert state.status == "failed"

    def test_post_iteration_escape_aborts(self, project: Path, ticket_path: Path) -> None:
        """If worktree branch changes after agent call, abort."""
        thread_id, session_name = self.setup_for_loop(project, ticket_path)

        call_count = 0

        def branch_check_side_effect(worktree, expected):
            nonlocal call_count
            call_count += 1
            return call_count == 1  # Pre-loop passes, post-iteration fails

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "Working on it.\\n\\nSTATUS: WORKING", "session_id": "s1"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with (
            patch("kingdom.harness.check_worktree_branch", side_effect=branch_check_side_effect),
            patch("kingdom.harness.run_streaming_subprocess", return_value=mock_result),
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

        assert status == "failed"
        ticket = read_ticket(ticket_path)
        assert "BRANCH ESCAPE detected after iteration" in ticket.body
