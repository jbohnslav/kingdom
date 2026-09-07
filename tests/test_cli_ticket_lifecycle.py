"""Tests for ticket lifecycle commands."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, current_thread
from unittest.mock import patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app, ticket_pull, ticket_reopen, ticket_start
from kingdom.doctor import binding_issues, execution_context_issues
from kingdom.state import (
    ExecutionContext,
    archive_root,
    backlog_root,
    branch_root,
    clear_ticket_execution_contexts,
    ensure_branch_layout,
    list_execution_contexts,
    read_execution_ticket_context,
    record_execution_ticket_context,
    resolve_execution_context,
)
from kingdom.ticket import Ticket, find_ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


def create_ticket_in(directory: Path, ticket_id: str = "t001") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ticket = Ticket(
        id=ticket_id,
        status="open",
        title="Test ticket",
        body="Body text",
        created=datetime.now(UTC),
    )
    path = directory / f"{ticket_id}.md"
    write_ticket(ticket, path)
    return path


class TestTicketCreate:
    def test_create_echoes_id_and_title(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "My new ticket"])

        assert result.exit_code == 0, result.output
        output = result.output.strip()
        assert output.startswith("Created ")
        assert "My new ticket" in output

    def test_create_backlog_echoes_id_and_title(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Backlog ticket", "--backlog"])

        assert result.exit_code == 0, result.output
        output = result.output.strip()
        assert output.startswith("Created ")
        assert "(backlog)" in output
        assert "Backlog ticket" in output

    def test_create_non_backlog_omits_backlog_label(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Branch ticket"])

        assert result.exit_code == 0, result.output
        output = result.output.strip()
        assert output.startswith("Created ")
        assert "(backlog)" not in output

    def test_create_accepts_description_and_type_flags(self, cli_project: Path) -> None:
        result = runner.invoke(
            ticket_app,
            ["create", "Typed ticket", "-d", "Body from flag", "--type", "bug"],
        )

        assert result.exit_code == 0, result.output
        # Extract ticket ID from "Created <id>: <title>"
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        created_ticket = found.ticket
        assert created_ticket.body == "Body from flag\n\n## Acceptance Criteria\n\n- [ ]"
        assert created_ticket.type == "bug"

    def test_create_accepts_title_and_body_flags(self, cli_project: Path) -> None:
        result = runner.invoke(
            ticket_app,
            ["create", "--title", "Flag title", "--body", "Body from body flag"],
        )

        assert result.exit_code == 0, result.output
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        created_ticket = found.ticket
        assert created_ticket.title == "Flag title"
        assert created_ticket.body == "Body from body flag\n\n## Acceptance Criteria\n\n- [ ]"

    def test_create_accepts_short_title_and_body_flags(self, cli_project: Path) -> None:
        result = runner.invoke(
            ticket_app,
            ["create", "-t", "Short flag title", "-b", "Body from short flag"],
        )

        assert result.exit_code == 0, result.output
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        created_ticket = found.ticket
        assert created_ticket.title == "Short flag title"
        assert created_ticket.body == "Body from short flag\n\n## Acceptance Criteria\n\n- [ ]"

    def test_create_accepts_long_type_flag(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Typed ticket", "--type", "feature"])

        assert result.exit_code == 0, result.output
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        created_ticket = found.ticket
        assert created_ticket.type == "feature"

    @pytest.mark.parametrize("title_flag", ["-t", "--title"])
    def test_create_rejects_duplicate_title_sources(self, cli_project: Path, title_flag: str) -> None:
        result = runner.invoke(ticket_app, ["create", "Positional title", title_flag, "Flag title"])

        assert result.exit_code == 1
        assert "either positionally or with --title" in result.output

    def test_create_rejects_duplicate_body_sources(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Body conflict", "-d", "Description", "-b", "Body"])

        assert result.exit_code == 1
        assert "either --description or --body" in result.output

    def test_create_out_of_range_priority_rejects(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Bad priority", "-p", "5"])
        assert result.exit_code == 1
        assert "out of range" in result.output.lower() or "invalid priority" in result.output.lower()

    def test_create_with_p_prefix_priority(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "P-prefix test", "-p", "p1"])
        assert result.exit_code == 0

        output = result.output.strip()
        ticket_id = output.split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        created_ticket = found.ticket
        assert created_ticket.priority == 1

    def test_create_no_trailing_whitespace(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Whitespace check"])

        assert result.exit_code == 0
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        ticket_path = found.path
        content = ticket_path.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            assert line == line.rstrip(), f"Line {i} has trailing whitespace: {line!r}"

    def test_create_prints_file_path(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Path ticket"])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().splitlines()
        assert len(lines) == 2
        # First line is the "Created <id>: <title>" message
        assert lines[0].startswith("Created ")
        # Second line is the file path
        assert lines[1].endswith(".md")
        assert Path(lines[1]).exists()

    def test_create_backlog_prints_file_path(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Backlog path ticket", "--backlog"])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().splitlines()
        assert len(lines) == 2
        assert lines[1].endswith(".md")
        assert "backlog" in lines[1]
        assert Path(lines[1]).exists()


class TestTicketCreateOptions:
    """Tests for new create options: --parent, --tags."""

    def test_create_with_parent(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Parent", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        result = runner.invoke(ticket_app, ["create", "Child ticket", "--parent", "aaaa"])
        assert result.exit_code == 0

        # Find the created ticket
        created_files = [f for f in tickets_dir.glob("*.md") if f.stem != "aaaa"]
        assert len(created_files) == 1
        child = read_ticket(created_files[0])
        assert child.parent == "aaaa"

    def test_create_with_tags(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Tagged ticket", "--tags", "frontend,polish"])
        assert result.exit_code == 0

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        created_files = list(tickets_dir.glob("*.md"))
        assert len(created_files) == 1
        ticket = read_ticket(created_files[0])
        assert "frontend" in ticket.tags
        assert "polish" in ticket.tags

    def test_create_with_ac_flags(self, cli_project: Path) -> None:
        result = runner.invoke(
            ticket_app,
            ["create", "AC ticket", "--ac", "Tests pass", "--ac", "No regressions"],
        )
        assert result.exit_code == 0, result.output

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        created_files = list(tickets_dir.glob("*.md"))
        assert len(created_files) == 1
        ticket = read_ticket(created_files[0])
        assert "- [ ] Tests pass" in ticket.body
        assert "- [ ] No regressions" in ticket.body
        assert "## Acceptance Criteria" in ticket.body

    def test_create_with_description_and_ac(self, cli_project: Path) -> None:
        result = runner.invoke(
            ticket_app,
            [
                "create",
                "Full ticket",
                "-d",
                "Timeout handler bug",
                "--ac",
                "Tests pass",
                "--ac",
                "No regressions",
            ],
        )
        assert result.exit_code == 0, result.output

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        created_files = list(tickets_dir.glob("*.md"))
        assert len(created_files) == 1
        ticket = read_ticket(created_files[0])
        assert ticket.body == (
            "Timeout handler bug\n\n## Acceptance Criteria\n\n- [ ] Tests pass\n- [ ] No regressions"
        )

    def test_create_description_without_ac_still_has_ac_section(self, cli_project: Path) -> None:
        """When -d is provided without --ac, the AC section should still be present."""
        result = runner.invoke(
            ticket_app,
            ["create", "Desc only", "-d", "Some description"],
        )
        assert result.exit_code == 0, result.output

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        created_files = list(tickets_dir.glob("*.md"))
        assert len(created_files) == 1
        ticket = read_ticket(created_files[0])
        assert "## Acceptance Criteria" in ticket.body
        assert "- [ ]" in ticket.body
        assert ticket.body.startswith("Some description")


class TestTicketCloseArchive:
    def test_close_backlog_ticket_archives(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        path = create_ticket_in(backlog_dir, "arch")

        result = runner.invoke(ticket_app, ["close", "arch"])

        assert result.exit_code == 0, result.output
        assert "closed" in result.output
        # Should have moved to archive
        assert not path.exists()
        archived = archive_root(cli_project) / "backlog" / "tickets" / "arch.md"
        assert archived.exists()

    def test_close_branch_ticket_stays_in_place(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "stay")

        result = runner.invoke(ticket_app, ["close", "stay"])

        assert result.exit_code == 0, result.output
        # Should still be in the branch
        assert path.exists()

    def test_reopen_archived_backlog_ticket_restores(self, cli_project: Path) -> None:
        # Create a closed ticket directly in archive
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ticket = Ticket(
            id="rest",
            status="closed",
            title="Archived ticket",
            body="Body",
            created=datetime.now(UTC),
        )
        archived_path = archive_dir / "rest.md"
        write_ticket(ticket, archived_path)

        result = runner.invoke(ticket_app, ["reopen", "rest"])

        assert result.exit_code == 0, result.output
        # Should have moved back to backlog
        assert not archived_path.exists()
        restored = backlog_root(cli_project) / "tickets" / "rest.md"
        assert restored.exists()

    def test_start_archived_backlog_ticket_restores(self, cli_project: Path) -> None:
        # Create a closed ticket in archive
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ticket = Ticket(
            id="strt",
            status="closed",
            title="Start me",
            body="Body",
            created=datetime.now(UTC),
        )
        archived_path = archive_dir / "strt.md"
        write_ticket(ticket, archived_path)

        with patch.dict(os.environ, {"TERM_SESSION_ID": "archived-backlog-terminal-test"}, clear=True):
            result = runner.invoke(ticket_app, ["start", "strt"])

            assert result.exit_code == 0, result.output
            context = read_execution_ticket_context(cli_project, resolve_execution_context())

        assert not archived_path.exists()
        restored = backlog_root(cli_project) / "tickets" / "strt.md"
        assert restored.exists()
        assert context is not None
        assert context["ticket_id"] == "strt"
        assert context["location"] == "backlog"

    def test_start_assigns_ticket_to_execution_context(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(branch_dir, "hand")

        with patch.dict(os.environ, {"KD_CONTEXT": "assignment-session"}, clear=True):
            result = runner.invoke(ticket_app, ["start", "hand"])
            context = resolve_execution_context()

        assert result.exit_code == 0, result.output
        assert context is not None
        ticket = read_ticket(ticket_path)
        assert ticket.status == "in_progress"
        assert ticket.assignee == context.context_id

    def test_start_overwrites_existing_assignee_with_context(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="asgn",
            status="open",
            title="Assigned elsewhere",
            body="",
            assignee="alice",
            created=datetime.now(UTC),
        )
        ticket_path = branch_dir / "asgn.md"
        write_ticket(ticket, ticket_path)

        with patch.dict(os.environ, {"KD_CONTEXT": "replacement-session"}, clear=True):
            result = runner.invoke(ticket_app, ["start", "asgn"])
            context = resolve_execution_context()

        assert result.exit_code == 0, result.output
        assert context is not None
        assert read_ticket(ticket_path).assignee == context.context_id

    def test_concurrent_starts_by_one_context_leave_one_ticket_bound(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        first_path = create_ticket_in(branch_dir, "race-a")
        second_path = create_ticket_in(branch_dir, "race-b")
        context = resolve_execution_context(
            session_id="shared-owner",
            host="codex",
            cwd=cli_project,
            prefer_session_id=True,
        )
        assert context is not None

        first_reached_record = Event()
        second_finished_record = Event()
        release_first = Event()

        def delayed_record(
            base: Path,
            current: ExecutionContext,
            ticket_id: str,
            *,
            feature: str,
            location: str | None = None,
        ) -> None:
            if current_thread().name.endswith("_0"):
                first_reached_record.set()
                assert release_first.wait(timeout=2)
            record_execution_ticket_context(
                base,
                current,
                ticket_id,
                feature=feature,
                location=location,
            )
            if current_thread().name.endswith("_1"):
                second_finished_record.set()

        with (
            patch("kingdom.cli.ticket.resolve_execution_context", return_value=context),
            patch("kingdom.cli.ticket.record_execution_ticket_context", side_effect=delayed_record),
            ThreadPoolExecutor(max_workers=2, thread_name_prefix="starter") as pool,
        ):
            first_future = pool.submit(ticket_start, "race-a")
            assert first_reached_record.wait(timeout=2)
            second_future = pool.submit(ticket_start, "race-b")
            assert not second_finished_record.wait(timeout=0.5)
            release_first.set()
            first_future.result(timeout=2)
            second_future.result(timeout=2)

        binding = read_execution_ticket_context(cli_project, context)
        assert read_ticket(first_path).assignee is None
        assert read_ticket(second_path).assignee == context.context_id
        assert binding is not None
        assert binding["ticket_id"] == "race-b"
        assert binding_issues(cli_project) == []
        assert execution_context_issues(cli_project) == []

    def test_concurrent_reassignment_does_not_unassign_new_owner(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        next_path = create_ticket_in(branch_dir, "next")
        previous_path = create_ticket_in(branch_dir, "previous")
        first = resolve_execution_context(
            session_id="first-owner",
            host="codex",
            cwd=cli_project,
            prefer_session_id=True,
        )
        second = resolve_execution_context(
            session_id="second-owner",
            host="codex",
            cwd=cli_project,
            prefer_session_id=True,
        )
        assert first is not None
        assert second is not None
        previous = read_ticket(previous_path)
        previous.status = "in_progress"
        previous.assignee = first.context_id
        write_ticket(previous, previous_path)
        record_execution_ticket_context(
            cli_project,
            first,
            previous.id,
            feature=BRANCH,
            location=f"branch:{BRANCH}",
        )

        first_reached_stale_write = Event()
        second_finished = Event()
        release_first = Event()

        def current_context() -> ExecutionContext:
            return first if current_thread().name.endswith("_0") else second

        def delayed_write(ticket: Ticket, path: Path) -> None:
            if current_thread().name.endswith("_0") and ticket.id == previous.id and ticket.assignee is None:
                first_reached_stale_write.set()
                assert release_first.wait(timeout=2)
            write_ticket(ticket, path)

        def start_as_second() -> None:
            ticket_start(previous.id)
            second_finished.set()

        with (
            patch("kingdom.cli.ticket.resolve_execution_context", side_effect=current_context),
            patch("kingdom.cli.ticket.write_ticket", side_effect=delayed_write),
            ThreadPoolExecutor(max_workers=2, thread_name_prefix="starter") as pool,
        ):
            first_future = pool.submit(ticket_start, "next")
            assert first_reached_stale_write.wait(timeout=2)
            second_future = pool.submit(start_as_second)
            assert not second_finished.wait(timeout=0.5)
            release_first.set()
            first_future.result(timeout=2)
            second_future.result(timeout=2)

        contexts = {
            binding["context_id"]: binding["ticket_id"]
            for binding in list_execution_contexts(cli_project, feature=BRANCH)
            if binding.get("active") and binding.get("ticket_id")
        }
        assert read_ticket(next_path).assignee == first.context_id
        assert read_ticket(previous_path).assignee == second.context_id
        assert contexts == {
            first.context_id: "next",
            second.context_id: previous.id,
        }
        assert binding_issues(cli_project) == []
        assert execution_context_issues(cli_project) == []

    def test_pull_start_serializes_with_direct_start(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        direct_path = create_ticket_in(branch_dir, "direct-race")
        pulled_path = create_ticket_in(backlog_root(cli_project) / "tickets", "pull-race")
        context = resolve_execution_context(
            session_id="shared-pull-owner",
            host="codex",
            cwd=cli_project,
            prefer_session_id=True,
        )
        assert context is not None

        direct_reached_record = Event()
        pull_finished = Event()
        release_direct = Event()

        def delayed_record(
            base: Path,
            current: ExecutionContext,
            ticket_id: str,
            *,
            feature: str,
            location: str | None = None,
        ) -> None:
            if current_thread().name.endswith("_0"):
                direct_reached_record.set()
                assert release_direct.wait(timeout=2)
            record_execution_ticket_context(
                base,
                current,
                ticket_id,
                feature=feature,
                location=location,
            )

        def pull_and_start() -> None:
            ticket_pull(["pull-race"], start=True)
            pull_finished.set()

        with (
            patch("kingdom.cli.ticket.resolve_execution_context", return_value=context),
            patch("kingdom.cli.ticket.record_execution_ticket_context", side_effect=delayed_record),
            ThreadPoolExecutor(max_workers=2, thread_name_prefix="starter") as pool,
        ):
            direct_future = pool.submit(ticket_start, "direct-race")
            assert direct_reached_record.wait(timeout=2)
            pull_future = pool.submit(pull_and_start)
            assert not pull_finished.wait(timeout=0.5)
            release_direct.set()
            direct_future.result(timeout=2)
            pull_future.result(timeout=2)

        pulled_path = branch_dir / pulled_path.name
        binding = read_execution_ticket_context(cli_project, context)
        assert read_ticket(direct_path).assignee is None
        assert read_ticket(pulled_path).assignee == context.context_id
        assert binding is not None
        assert binding["ticket_id"] == "pull-race"
        assert binding_issues(cli_project) == []
        assert execution_context_issues(cli_project) == []

    def test_reopen_serializes_ticket_clear_with_direct_start(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(branch_dir, "reopen-race")
        ticket = read_ticket(ticket_path)
        ticket.status = "closed"
        ticket.closed_at = datetime.now(UTC)
        ticket.resolution = "completed"
        write_ticket(ticket, ticket_path)
        reopening = resolve_execution_context(
            session_id="reopening-owner",
            host="codex",
            cwd=cli_project,
            prefer_session_id=True,
        )
        starting = resolve_execution_context(
            session_id="starting-owner",
            host="codex",
            cwd=cli_project,
            prefer_session_id=True,
        )
        assert reopening is not None
        assert starting is not None

        reopen_reached_clear = Event()
        start_finished = Event()
        release_reopen = Event()

        def current_context() -> ExecutionContext:
            return reopening if current_thread().name.endswith("_0") else starting

        def delayed_clear(base: Path, ticket_id: str, *, now: datetime | None = None) -> list[str]:
            if current_thread().name.endswith("_0"):
                reopen_reached_clear.set()
                assert release_reopen.wait(timeout=2)
            return clear_ticket_execution_contexts(base, ticket_id, now=now)

        def start_ticket() -> None:
            ticket_start("reopen-race")
            start_finished.set()

        with (
            patch("kingdom.cli.ticket.resolve_execution_context", side_effect=current_context),
            patch("kingdom.cli.ticket.clear_ticket_execution_contexts", side_effect=delayed_clear),
            ThreadPoolExecutor(max_workers=2, thread_name_prefix="starter") as pool,
        ):
            reopen_future = pool.submit(ticket_reopen, "reopen-race")
            assert reopen_reached_clear.wait(timeout=2)
            start_future = pool.submit(start_ticket)
            assert not start_finished.wait(timeout=0.5)
            release_reopen.set()
            reopen_future.result(timeout=2)
            start_future.result(timeout=2)

        binding = read_execution_ticket_context(cli_project, starting)
        ticket = read_ticket(ticket_path)
        assert ticket.status == "in_progress"
        assert ticket.assignee == starting.context_id
        assert binding is not None
        assert binding["ticket_id"] == ticket.id
        assert binding_issues(cli_project) == []
        assert execution_context_issues(cli_project) == []

    def test_start_without_active_session_does_not_mutate_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            branch_dir = branch_root(base, BRANCH) / "tickets"
            ticket_path = create_ticket_in(branch_dir, "nope")

            result = runner.invoke(ticket_app, ["start", "nope"])

            assert result.exit_code == 1
            assert "No active session" in result.output
            ticket = read_ticket(ticket_path)
            assert ticket.status == "open"
            assert ticket.assignee is None

    def test_start_records_execution_ticket_context(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "term")

        with patch.dict(os.environ, {"TERM_SESSION_ID": "terminal-ticket-test"}, clear=True):
            result = runner.invoke(ticket_app, ["start", "term"])

            assert result.exit_code == 0, result.output
            context = read_execution_ticket_context(cli_project, resolve_execution_context())

        assert context is not None
        assert context["ticket_id"] == "term"
        assert context["feature"] == "feature-ticket-test"
        assert context["location"] == "branch:feature-ticket-test"

    def test_start_records_backlog_execution_ticket_context_location(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "bctx")

        with patch.dict(os.environ, {"TERM_SESSION_ID": "backlog-terminal-ticket-test"}, clear=True):
            result = runner.invoke(ticket_app, ["start", "bctx"])

            assert result.exit_code == 0, result.output
            context = read_execution_ticket_context(cli_project, resolve_execution_context())

        assert context is not None
        assert context["ticket_id"] == "bctx"
        assert context["feature"] == "feature-ticket-test"
        assert context["location"] == "backlog"

    def test_start_records_archived_branch_execution_ticket_context_location(self, cli_project: Path) -> None:
        archive_dir = archive_root(cli_project) / "old-feature" / "tickets"
        create_ticket_in(archive_dir, "actx")

        with patch.dict(os.environ, {"TERM_SESSION_ID": "archived-branch-terminal-test"}, clear=True):
            result = runner.invoke(ticket_app, ["start", "actx"])

            assert result.exit_code == 0, result.output
            context = read_execution_ticket_context(cli_project, resolve_execution_context())

        ticket = read_ticket(archive_dir / "actx.md")
        assert ticket.status == "in_progress"
        assert ticket.assignee is not None
        assert ticket.assignee.startswith("terminal:")
        assert context is not None
        assert context["ticket_id"] == "actx"
        assert context["feature"] == "feature-ticket-test"
        assert context["location"] == "archive:old-feature"


class TestTicketStatus:
    def test_status_sets_arbitrary_value(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "stat")

        result = runner.invoke(ticket_app, ["status", "stat", "blocked"])

        assert result.exit_code == 0, result.output
        assert "open → blocked" in result.output
        ticket = read_ticket(branch_dir / "stat.md")
        assert ticket.status == "blocked"

    def test_status_round_trip(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "rt")

        runner.invoke(ticket_app, ["status", "rt", "in_review"])
        result = runner.invoke(ticket_app, ["status", "rt", "waiting"])

        assert result.exit_code == 0, result.output
        assert "in_review → waiting" in result.output

    def test_status_leaving_in_progress_clears_native_assignee(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "unassign")

        with patch.dict(os.environ, {"KD_CONTEXT": "status-unassign"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "unassign"]).exit_code == 0
            context = resolve_execution_context()
            assert context is not None

            result = runner.invoke(ticket_app, ["status", "unassign", "blocked"])
            binding = read_execution_ticket_context(cli_project, context)

        assert result.exit_code == 0, result.output
        assert read_ticket(path).assignee is None
        assert binding is None


class TestTicketCloseIdempotent:
    def test_close_already_archived_ticket_is_noop(self, cli_project: Path) -> None:
        """Closing an already-closed archived ticket should not double-move."""
        # Create a closed ticket directly in archive
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ticket = Ticket(
            id="idem",
            status="closed",
            resolution="completed",
            title="Already archived",
            body="Body",
            created=datetime.now(UTC),
        )
        archived_path = archive_dir / "idem.md"
        write_ticket(ticket, archived_path)

        result = runner.invoke(ticket_app, ["close", "idem"])

        assert result.exit_code == 0, result.output
        # Should still be in archive, not moved elsewhere
        assert archived_path.exists()
        # Should NOT be in backlog
        assert not (backlog_root(cli_project) / "tickets" / "idem.md").exists()

    def test_close_rejects_changing_an_existing_resolution(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="final",
            status="closed",
            title="Already completed",
            body="Body",
            created=datetime.now(UTC),
            closed_at=datetime(2026, 8, 1, tzinfo=UTC),
            resolution="completed",
        )
        path = branch_dir / "final.md"
        write_ticket(ticket, path)

        result = runner.invoke(
            ticket_app,
            ["close", "final", "--resolution", "wont-do", "--reason", "Changed our mind"],
        )

        assert result.exit_code == 1
        assert "already closed with resolution completed" in result.output
        assert "reopen final" in result.output
        unchanged = read_ticket(path)
        assert unchanged.resolution == "completed"
        assert unchanged.closed_at == ticket.closed_at

    def test_close_rejects_new_reason_on_closed_ticket(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="rerun",
            status="closed",
            title="Already completed",
            body="Body",
            created=datetime.now(UTC),
            closed_at=datetime(2026, 8, 1, tzinfo=UTC),
            resolution="completed",
        )
        path = branch_dir / "rerun.md"
        write_ticket(ticket, path)

        result = runner.invoke(ticket_app, ["close", "rerun", "--reason", "New evidence"])

        assert result.exit_code == 1
        assert "already closed" in result.output
        assert "reopen rerun" in result.output
        unchanged = read_ticket(path)
        assert unchanged.body == "Body"
        assert unchanged.closed_at == ticket.closed_at

    def test_closed_ticket_requires_explicit_resolution(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="ldup",
            status="closed",
            title="Legacy duplicate",
            body="Body",
            created=datetime.now(UTC),
            closed_at=datetime(2026, 8, 1, tzinfo=UTC),
            duplicate_of="original",
        )
        path = branch_dir / "ldup.md"
        write_ticket(ticket, path)

        result = runner.invoke(ticket_app, ["close", "ldup"])

        assert result.exit_code == 1, result.output
        assert "missing a resolution" in result.output
        unchanged = read_ticket(path)
        assert unchanged.resolution is None
        assert unchanged.duplicate_of == "original"
        assert unchanged.closed_at == ticket.closed_at

    def test_closed_duplicate_validates_identical_duplicate_target(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "original")
        ticket = Ticket(
            id="ldup",
            status="closed",
            title="Legacy duplicate",
            body="Body",
            created=datetime.now(UTC),
            closed_at=datetime(2026, 8, 1, tzinfo=UTC),
            duplicate_of="original",
            resolution="duplicate",
            close_reason="Duplicate of original",
        )
        path = branch_dir / "ldup.md"
        write_ticket(ticket, path)

        result = runner.invoke(ticket_app, ["close", "ldup", "--duplicate-of", "original"])

        assert result.exit_code == 0, result.output
        assert "already closed (duplicate)" in result.output
        assert read_ticket(path).closed_at == ticket.closed_at

    def test_closed_ticket_does_not_bypass_duplicate_target_validation(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="ldup",
            status="closed",
            title="Legacy duplicate",
            body="Body",
            created=datetime.now(UTC),
            closed_at=datetime(2026, 8, 1, tzinfo=UTC),
            duplicate_of="original",
        )
        path = branch_dir / "ldup.md"
        write_ticket(ticket, path)

        result = runner.invoke(ticket_app, ["close", "ldup", "--duplicate-of", "nonexistent"])

        assert result.exit_code == 1
        assert "Duplicate target not found" in result.output
        assert read_ticket(path).closed_at == ticket.closed_at

    def test_closed_duplicate_rejects_different_existing_target(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "original")
        create_ticket_in(branch_dir, "other")
        ticket = Ticket(
            id="ldup",
            status="closed",
            resolution="duplicate",
            title="Legacy duplicate",
            body="Body",
            created=datetime.now(UTC),
            closed_at=datetime(2026, 8, 1, tzinfo=UTC),
            duplicate_of="original",
        )
        path = branch_dir / "ldup.md"
        write_ticket(ticket, path)

        result = runner.invoke(ticket_app, ["close", "ldup", "--duplicate-of", "other"])

        assert result.exit_code == 1
        assert "already closed" in result.output
        assert "reopen ldup" in result.output
        unchanged = read_ticket(path)
        assert unchanged.duplicate_of == "original"
        assert unchanged.closed_at == ticket.closed_at


class TestTicketCloseReason:
    def test_close_with_reason_appends_worklog(self, cli_project: Path) -> None:
        """Closing with --reason should add a worklog entry."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "reas")

        result = runner.invoke(ticket_app, ["close", "reas", "-m", "No longer needed"])

        assert result.exit_code == 0, result.output
        assert "closed" in result.output
        content = path.read_text()
        assert "## Worklog" in content
        assert "Closed: No longer needed" in content

    def test_close_with_long_reason_flag(self, cli_project: Path) -> None:
        """--reason should also work (long form of -m)."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "rsnl")

        result = runner.invoke(ticket_app, ["close", "rsnl", "--reason", "Duplicate of xyz"])

        assert result.exit_code == 0, result.output
        content = path.read_text()
        assert "Closed: Duplicate of xyz" in content

    def test_close_without_reason_no_worklog(self, cli_project: Path) -> None:
        """Closing without --reason should not add a worklog entry."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "nors")

        result = runner.invoke(ticket_app, ["close", "nors"])

        assert result.exit_code == 0, result.output
        content = path.read_text()
        assert "## Worklog" not in content


class TestTicketCloseResolution:
    def test_close_defaults_to_completed(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "done")

        result = runner.invoke(ticket_app, ["close", "done"])

        assert result.exit_code == 0, result.output
        ticket = read_ticket(path)
        assert ticket.resolution == "completed"
        assert ticket.closed_at is not None

    def test_close_accepts_each_non_completed_resolution(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"

        for resolution in ("wont-do", "invalid"):
            ticket_id = f"{resolution[:4]}"
            path = create_ticket_in(branch_dir, ticket_id)

            result = runner.invoke(
                ticket_app,
                ["close", ticket_id, "--resolution", resolution, "--reason", f"Marked {resolution}"],
            )

            assert result.exit_code == 0, result.output
            assert read_ticket(path).resolution == resolution

    def test_reference_resolutions_require_reference_without_mutation(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"

        for resolution, option in (("duplicate", "--duplicate-of"), ("superseded", "--superseded-by")):
            ticket_id = f"missing-{resolution}"
            path = create_ticket_in(branch_dir, ticket_id)
            with patch.dict(os.environ, {"KD_CONTEXT": f"missing-{resolution}"}, clear=True):
                assert runner.invoke(ticket_app, ["start", ticket_id]).exit_code == 0
                context = resolve_execution_context()
                assert context is not None
                original = path.read_text(encoding="utf-8")

                result = runner.invoke(
                    ticket_app,
                    ["close", ticket_id, "--resolution", resolution, "--reason", f"Marked {resolution}"],
                )
                binding = read_execution_ticket_context(cli_project, context)

            assert result.exit_code == 1
            assert f"requires {option}" in result.output
            assert path.read_text(encoding="utf-8") == original
            assert binding is not None
            assert binding["ticket_id"] == ticket_id

    def test_non_completed_resolution_requires_reason_without_mutation(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "nore")

        with patch.dict(os.environ, {"KD_CONTEXT": "resolution-validation"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "nore"]).exit_code == 0
            context = resolve_execution_context()
            assert context is not None

            result = runner.invoke(ticket_app, ["close", "nore", "--resolution", "wont-do", "-m", "   "])

            binding = read_execution_ticket_context(cli_project, context)

        assert result.exit_code == 1
        assert "requires a non-empty --reason" in result.output
        assert "nore --resolution wont-do --reason" in result.output
        ticket = read_ticket(path)
        assert ticket.status == "in_progress"
        assert ticket.resolution is None
        assert ticket.closed_at is None
        assert binding is not None
        assert binding["ticket_id"] == "nore"

    def test_invalid_resolution_lists_valid_choices(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "badr")

        result = runner.invoke(ticket_app, ["close", "badr", "--resolution", "abandoned", "-m", "No"])

        assert result.exit_code == 2
        assert "completed" in result.output
        assert "wont-do" in result.output
        assert "duplicate" in result.output
        assert "superseded" in result.output
        assert "invalid" in result.output
        assert read_ticket(path).status == "open"

    def test_close_records_context_and_uses_one_timestamp_for_binding_cleanup(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "attr")

        with patch.dict(os.environ, {"KD_CONTEXT": "resolution-attribution"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "attr"]).exit_code == 0
            context = resolve_execution_context()
            assert context is not None

            result = runner.invoke(ticket_app, ["close", "attr"])

            binding = read_execution_ticket_context(cli_project, context)

        assert result.exit_code == 0, result.output
        ticket = read_ticket(path)
        assert ticket.closed_context == context.context_id
        assert ticket.closed_at is not None
        assert binding is None

        context_path = next((cli_project / ".kd" / "runtime" / "contexts").glob("*.json"))
        context_data = json.loads(context_path.read_text())
        assert context_data["unbound_at"] == ticket.closed_at.isoformat()


class TestTicketLifecycleHistory:
    def test_close_records_structured_reason_and_lifecycle_event(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "hist")

        with patch.dict(os.environ, {"KD_CONTEXT": "lifecycle-close"}, clear=True):
            result = runner.invoke(
                ticket_app,
                ["close", "hist", "--resolution", "wont-do", "--reason", "Out of scope: later"],
            )

        assert result.exit_code == 0, result.output
        ticket = read_ticket(path)
        assert ticket.close_reason == "Out of scope: later"
        assert "## Lifecycle" in ticket.body
        assert "closed (wont-do)" in ticket.body
        assert "Out of scope: later" in ticket.body
        assert ticket.closed_context in ticket.body
        content = path.read_text()
        assert "close_reason:" in content
        assert "## Worklog" in content
        assert "Closed: Out of scope: later" in content

    def test_close_reopen_close_history_is_append_only(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "cycle")
        create_ticket_in(branch_dir, "next")

        with patch.dict(os.environ, {"KD_CONTEXT": "lifecycle-cycle"}, clear=True):
            first_close = runner.invoke(
                ticket_app,
                ["close", "cycle", "--resolution", "wont-do", "--reason", "First decision"],
            )
            reopen = runner.invoke(ticket_app, ["reopen", "cycle"])
            second_close = runner.invoke(ticket_app, ["close", "cycle", "--superseded-by", "next"])

        assert first_close.exit_code == 0, first_close.output
        assert reopen.exit_code == 0, reopen.output
        assert second_close.exit_code == 0, second_close.output
        ticket = read_ticket(path)
        assert ticket.resolution == "superseded"
        assert ticket.close_reason == "Superseded by next"
        assert ticket.superseded_by == "next"
        assert ticket.body.count("— closed (") == 2
        assert ticket.body.count("— reopened") == 1
        first_position = ticket.body.index("First decision")
        reopen_position = ticket.body.index("— reopened")
        second_position = ticket.body.index("Superseded by next", reopen_position)
        assert first_position < reopen_position < second_position

    def test_reopen_clears_active_closure_and_preserves_legacy_history(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="open",
            status="closed",
            title="Reopen me",
            body=(
                "Legacy details\n\n## Worklog\n\n- old close note\n\n"
                "## Lifecycle\n\n- 2026-01-01T00:00:00Z — closed (duplicate): Same work"
            ),
            created=datetime(2026, 1, 1, tzinfo=UTC),
            closed_at=datetime(2026, 1, 2, tzinfo=UTC),
            resolution="duplicate",
            close_reason="Same work",
            closed_context="codex:old",
            duplicate_of="original",
        )
        path = branch_dir / "open.md"
        write_ticket(ticket, path)

        with patch.dict(os.environ, {"KD_CONTEXT": "lifecycle-reopen"}, clear=True):
            result = runner.invoke(ticket_app, ["reopen", "open"])

        assert result.exit_code == 0, result.output
        reopened = read_ticket(path)
        assert reopened.status == "open"
        assert reopened.closed_at is None
        assert reopened.resolution is None
        assert reopened.close_reason is None
        assert reopened.closed_context is None
        assert reopened.duplicate_of is None
        assert reopened.superseded_by is None
        assert "Legacy details" in reopened.body
        assert "- old close note" in reopened.body
        assert "closed (duplicate): Same work" in reopened.body
        assert "— reopened (previous: duplicate)" in reopened.body

    def test_reopen_clears_stale_native_assignee(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="reopen-owner",
            status="closed",
            title="Reopen stale owner",
            created=datetime(2026, 1, 1, tzinfo=UTC),
            closed_at=datetime(2026, 1, 2, tzinfo=UTC),
            resolution="completed",
            assignee="codex:stale-owner",
        )
        path = branch_dir / "reopen-owner.md"
        write_ticket(ticket, path)

        result = runner.invoke(ticket_app, ["reopen", "reopen-owner"])

        assert result.exit_code == 0, result.output
        assert read_ticket(path).assignee is None

    def test_close_and_reopen_reject_malformed_context_without_mutation(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        close_path = create_ticket_in(branch_dir, "bad-close")
        reopen_path = branch_dir / "bad-reopen.md"
        write_ticket(
            Ticket(
                id="bad-reopen",
                status="closed",
                title="Closed ticket",
                created=datetime(2026, 1, 1, tzinfo=UTC),
                closed_at=datetime(2026, 1, 2, tzinfo=UTC),
                resolution="completed",
            ),
            reopen_path,
        )
        original_close = close_path.read_text(encoding="utf-8")
        original_reopen = reopen_path.read_text(encoding="utf-8")

        with patch.dict(os.environ, {"KD_CONTEXT": "malformed\ncontext"}, clear=True):
            close_result = runner.invoke(ticket_app, ["close", "bad-close"])
            reopen_result = runner.invoke(ticket_app, ["reopen", "bad-reopen"])

        for result in (close_result, reopen_result):
            assert result.exit_code == 1
            assert "KD_CONTEXT must be a single-line identifier" in result.output
            assert "Traceback" not in result.output
        assert close_path.read_text(encoding="utf-8") == original_close
        assert reopen_path.read_text(encoding="utf-8") == original_reopen

    def test_superseded_by_rejects_missing_target_without_mutation(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "old")

        result = runner.invoke(ticket_app, ["close", "old", "--superseded-by", "missing"])

        assert result.exit_code == 1
        assert "Superseding ticket not found" in result.output
        ticket = read_ticket(path)
        assert ticket.status == "open"
        assert ticket.resolution is None
        assert ticket.superseded_by is None


class TestTicketContextLifecycle:
    def test_start_without_execution_context_does_not_mutate_ticket(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(branch_dir, "noctx")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("os.ttyname", side_effect=OSError),
        ):
            result = runner.invoke(ticket_app, ["start", "noctx"])

        assert result.exit_code == 1
        assert "Set KD_CONTEXT" in result.output
        assert read_ticket(ticket_path).status == "open"

    def test_close_clears_execution_context_binding(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "ctxc")

        with patch.dict(os.environ, {"KD_CONTEXT": "close-session"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "ctxc"]).exit_code == 0
            context = resolve_execution_context()
            assert context is not None
            assert read_execution_ticket_context(cli_project, context) is not None

            result = runner.invoke(ticket_app, ["close", "ctxc"])

            assert result.exit_code == 0, result.output
            assert read_execution_ticket_context(cli_project, context) is None

            assert runner.invoke(ticket_app, ["reopen", "ctxc"]).exit_code == 0
            current = runner.invoke(ticket_app, ["current"])

            assert current.exit_code == 1
            assert "No ticket bound" in current.output

    def test_reopen_clears_terminal_binding_retained_after_interrupted_close(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(branch_dir, "term-interrupted")

        with patch.dict(
            os.environ,
            {"KD_CONTEXT": "interrupted-session", "TERM_SESSION_ID": "interrupted-terminal"},
            clear=True,
        ):
            assert runner.invoke(ticket_app, ["start", "term-interrupted"]).exit_code == 0
            ticket = read_ticket(ticket_path)
            ticket.status = "closed"
            ticket.closed_at = datetime.now(UTC)
            ticket.resolution = "completed"
            write_ticket(ticket, ticket_path)

            result = runner.invoke(ticket_app, ["reopen", "term-interrupted"])

            assert result.exit_code == 0, result.output
            assert read_execution_ticket_context(cli_project, resolve_execution_context()) is None

    def test_start_switches_binding_and_unassigns_previous_ticket(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        first_path = create_ticket_in(branch_dir, "one1")
        second_path = create_ticket_in(branch_dir, "two2")

        with patch.dict(os.environ, {"KD_CONTEXT": "switch-session"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "one1"]).exit_code == 0
            assert runner.invoke(ticket_app, ["start", "two2"]).exit_code == 0
            current = runner.invoke(ticket_app, ["current", "--id"])

        assert current.output.strip() == "two2"
        assert read_ticket(first_path).assignee is None
        assert read_ticket(second_path).assignee is not None


class TestTicketCloseDuplicate:
    def test_duplicate_of_sets_field_and_closes(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "dup1")
        create_ticket_in(branch_dir, "orig")

        result = runner.invoke(ticket_app, ["close", "dup1", "--duplicate-of", "orig"])

        assert result.exit_code == 0, result.output
        assert "closed" in result.output
        ticket = read_ticket(branch_dir / "dup1.md")
        assert ticket.status == "closed"
        assert ticket.duplicate_of == "orig"
        assert ticket.resolution == "duplicate"
        assert ticket.close_reason == "Duplicate of orig"
        assert "reference: orig" in ticket.body

    def test_duplicate_of_accepts_matching_explicit_resolution(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "dupe")
        create_ticket_in(branch_dir, "original")

        result = runner.invoke(
            ticket_app,
            ["close", "dupe", "--resolution", "duplicate", "--duplicate-of", "original"],
        )

        assert result.exit_code == 0, result.output
        ticket = read_ticket(branch_dir / "dupe.md")
        assert ticket.resolution == "duplicate"
        assert ticket.duplicate_of == "original"

    def test_duplicate_of_rejects_conflicting_resolution(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "conf")
        create_ticket_in(branch_dir, "original")

        result = runner.invoke(
            ticket_app,
            [
                "close",
                "conf",
                "--resolution",
                "superseded",
                "--duplicate-of",
                "original",
                "--reason",
                "Conflicting options",
            ],
        )

        assert result.exit_code == 1
        assert "--duplicate-of requires --resolution duplicate" in result.output
        assert "omit --resolution" in result.output
        ticket = read_ticket(path)
        assert ticket.status == "open"
        assert ticket.resolution is None
        assert ticket.duplicate_of is None

    def test_duplicate_of_adds_worklog(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "dup2")
        create_ticket_in(branch_dir, "xyz")

        runner.invoke(ticket_app, ["close", "dup2", "--duplicate-of", "xyz"])

        content = path.read_text()
        assert "Closed: Duplicate of xyz" in content

    def test_duplicate_of_with_custom_reason(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "dup3")
        create_ticket_in(branch_dir, "xyz")

        runner.invoke(ticket_app, ["close", "dup3", "--duplicate-of", "xyz", "-m", "Merged into xyz"])

        content = path.read_text()
        assert "Closed: Merged into xyz" in content

    def test_duplicate_of_serialized_in_frontmatter(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "dup4")
        create_ticket_in(branch_dir, "orig")

        runner.invoke(ticket_app, ["close", "dup4", "--duplicate-of", "orig"])

        content = (branch_dir / "dup4.md").read_text()
        assert "duplicate-of: orig" in content


class TestTicketCloseDuplicateValidation:
    def test_duplicate_of_rejects_nonexistent_target(self, cli_project: Path) -> None:
        """--duplicate-of should fail if the target ticket doesn't exist."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "dup1")

        result = runner.invoke(ticket_app, ["close", "dup1", "--duplicate-of", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "nonexistent" in result.output.lower()
        # Ticket should NOT be closed
        ticket = read_ticket(branch_dir / "dup1.md")
        assert ticket.status != "closed"

    def test_duplicate_of_rejects_self_reference(self, cli_project: Path) -> None:
        """--duplicate-of should fail if the target is the same ticket."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "self")

        result = runner.invoke(ticket_app, ["close", "self", "--duplicate-of", "self"])

        assert result.exit_code == 1
        assert "itself" in result.output.lower() or "self" in result.output.lower()
        ticket = read_ticket(branch_dir / "self.md")
        assert ticket.status != "closed"

    def test_duplicate_of_stores_canonical_id(self, cli_project: Path) -> None:
        """--duplicate-of should resolve and store the full canonical ticket ID."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "dup5")
        create_ticket_in(branch_dir, "target")

        # Use partial ID
        result = runner.invoke(ticket_app, ["close", "dup5", "--duplicate-of", "target"])

        assert result.exit_code == 0, result.output
        ticket = read_ticket(branch_dir / "dup5.md")
        assert ticket.duplicate_of == "target"


class TestTicketCloseUnblocked:
    def test_close_shows_newly_unblocked_ticket(self, cli_project: Path) -> None:
        """Closing a dep should print the ticket that becomes unblocked."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        # Create blocker ticket (open)
        blocker = Ticket(id="blk1", status="open", title="Blocker", body="", created=datetime.now(UTC))
        write_ticket(blocker, tickets_dir / "blk1.md")

        # Create blocked ticket that depends on blocker
        blocked = Ticket(
            id="dep1",
            status="open",
            title="Waiting on blocker",
            body="",
            deps=["blk1"],
            created=datetime.now(UTC),
        )
        write_ticket(blocked, tickets_dir / "dep1.md")

        result = runner.invoke(ticket_app, ["close", "blk1"])

        assert result.exit_code == 0, result.output
        assert "Unblocked 1 ticket(s):" in result.output
        assert "dep1" in result.output
        assert "Waiting on blocker" in result.output

    def test_close_no_unblocked_when_other_deps_remain(self, cli_project: Path) -> None:
        """If the blocked ticket has other open deps, it should NOT be listed."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        blocker1 = Ticket(id="bk01", status="open", title="Blocker 1", body="", created=datetime.now(UTC))
        blocker2 = Ticket(id="bk02", status="open", title="Blocker 2", body="", created=datetime.now(UTC))
        blocked = Ticket(
            id="dep2",
            status="open",
            title="Needs both",
            body="",
            deps=["bk01", "bk02"],
            created=datetime.now(UTC),
        )
        write_ticket(blocker1, tickets_dir / "bk01.md")
        write_ticket(blocker2, tickets_dir / "bk02.md")
        write_ticket(blocked, tickets_dir / "dep2.md")

        # Close only the first blocker
        result = runner.invoke(ticket_app, ["close", "bk01"])

        assert result.exit_code == 0, result.output
        assert "Unblocked" not in result.output

    def test_close_unblocked_when_all_deps_closed(self, cli_project: Path) -> None:
        """Closing the last open dep should show the ticket as unblocked."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        blocker1 = Ticket(id="bk11", status="closed", title="Already closed", body="", created=datetime.now(UTC))
        blocker2 = Ticket(id="bk12", status="open", title="Last blocker", body="", created=datetime.now(UTC))
        blocked = Ticket(
            id="dep3",
            status="open",
            title="Almost free",
            body="",
            deps=["bk11", "bk12"],
            created=datetime.now(UTC),
        )
        write_ticket(blocker1, tickets_dir / "bk11.md")
        write_ticket(blocker2, tickets_dir / "bk12.md")
        write_ticket(blocked, tickets_dir / "dep3.md")

        # Close the last blocker
        result = runner.invoke(ticket_app, ["close", "bk12"])

        assert result.exit_code == 0, result.output
        assert "Unblocked 1 ticket(s):" in result.output
        assert "dep3" in result.output
        assert "Almost free" in result.output

    def test_close_no_message_when_no_deps(self, cli_project: Path) -> None:
        """Closing a ticket nobody depends on should not print unblocked message."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        standalone = Ticket(id="solo", status="open", title="Standalone", body="", created=datetime.now(UTC))
        write_ticket(standalone, tickets_dir / "solo.md")

        result = runner.invoke(ticket_app, ["close", "solo"])

        assert result.exit_code == 0, result.output
        assert "Unblocked" not in result.output

    def test_close_multiple_unblocked(self, cli_project: Path) -> None:
        """Closing one blocker can unblock multiple tickets."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        blocker = Ticket(id="bk21", status="open", title="Big blocker", body="", created=datetime.now(UTC))
        dep_a = Ticket(
            id="da01",
            status="open",
            title="Task A",
            body="",
            deps=["bk21"],
            created=datetime.now(UTC),
        )
        dep_b = Ticket(
            id="db01",
            status="open",
            title="Task B",
            body="",
            deps=["bk21"],
            created=datetime.now(UTC),
        )
        write_ticket(blocker, tickets_dir / "bk21.md")
        write_ticket(dep_a, tickets_dir / "da01.md")
        write_ticket(dep_b, tickets_dir / "db01.md")

        result = runner.invoke(ticket_app, ["close", "bk21"])

        assert result.exit_code == 0, result.output
        assert "Unblocked 2 ticket(s):" in result.output
        assert "da01" in result.output
        assert "db01" in result.output

    def test_close_does_not_show_already_closed_dependents(self, cli_project: Path) -> None:
        """Already-closed tickets that depend on the blocker should not appear as unblocked."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        blocker = Ticket(id="bk31", status="open", title="Blocker", body="", created=datetime.now(UTC))
        already_closed = Ticket(
            id="ac01",
            status="closed",
            title="Already done",
            body="",
            deps=["bk31"],
            created=datetime.now(UTC),
        )
        write_ticket(blocker, tickets_dir / "bk31.md")
        write_ticket(already_closed, tickets_dir / "ac01.md")

        result = runner.invoke(ticket_app, ["close", "bk31"])

        assert result.exit_code == 0, result.output
        assert "Unblocked" not in result.output


class TestTicketCloseActivePeasantWarning:
    """Closing a ticket with an active peasant should warn."""

    def test_warns_when_peasant_active(self, cli_project: Path) -> None:
        from kingdom.session import update_agent_state

        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "pwrn")

        # Create an active peasant session for this ticket
        update_agent_state(cli_project, BRANCH, "peasant-pwrn", status="working", ticket="pwrn")

        result = runner.invoke(ticket_app, ["close", "pwrn"])

        assert result.exit_code == 0
        assert "closed" in result.output
        assert "Warning" in result.output
        assert "peasant-pwrn" in result.output

    def test_no_warning_when_no_peasant(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "nop")

        result = runner.invoke(ticket_app, ["close", "nop"])

        assert result.exit_code == 0
        assert "closed" in result.output
        assert "Warning" not in result.output

    def test_no_warning_for_stopped_peasant(self, cli_project: Path) -> None:
        from kingdom.session import update_agent_state

        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "stp")

        update_agent_state(cli_project, BRANCH, "peasant-stp", status="stopped", ticket="stp")

        result = runner.invoke(ticket_app, ["close", "stp"])

        assert result.exit_code == 0
        assert "Warning" not in result.output


class TestTicketClosed:
    """Tests for kd tk list --closed and kd tk close."""

    def test_lists_closed_tickets(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="closed", title="Done ticket", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        result = runner.invoke(ticket_app, ["list", "--closed"])
        assert result.exit_code == 0
        assert "aaaa" in result.output

    def test_closed_flag_includes_closed_with_open(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Open", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--closed"])
        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" in result.output

    def test_close_sets_closed_at(self, cli_project: Path) -> None:
        """kd tk close should set the closed_at timestamp."""
        from datetime import timedelta

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="To close", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )

        before = datetime.now(UTC)
        runner.invoke(ticket_app, ["close", "aaaa"])
        after = datetime.now(UTC)

        ticket = read_ticket(tickets_dir / "aaaa.md")
        assert ticket.closed_at is not None
        # Serialization truncates to seconds, so allow 1s tolerance
        assert before - timedelta(seconds=1) <= ticket.closed_at <= after + timedelta(seconds=1)

    def test_status_closed_filter(self, cli_project: Path) -> None:
        """kd tk list --status closed shows only closed tickets."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Open", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--status", "closed"])
        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output


class TestTicketDelete:
    def test_delete_removes_file(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "del1")

        result = runner.invoke(ticket_app, ["delete", "del1", "--force"])

        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output
        assert "del1" in result.output
        assert not path.exists()

    def test_delete_prevents_a_stale_snapshot_from_resurrecting_the_ticket(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "stale-delete")
        stale_ticket = read_ticket(path)

        result = runner.invoke(ticket_app, ["delete", "stale-delete", "--force"])
        stale_ticket.status = "closed"

        assert result.exit_code == 0, result.output
        with pytest.raises(FileNotFoundError, match="moved or deleted"):
            write_ticket(stale_ticket, path)
        assert not path.exists()

    def test_delete_not_found(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["delete", "nope", "--force"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_delete_cancelled(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "del2")

        result = runner.invoke(ticket_app, ["delete", "del2"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        assert path.exists()

    def test_delete_confirmed(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "del3")

        result = runner.invoke(ticket_app, ["delete", "del3"], input="y\n")

        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output
        assert not path.exists()

    def test_delete_blocked_by_active_peasant(self, cli_project: Path) -> None:
        from kingdom.session import update_agent_state

        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "del4")

        update_agent_state(cli_project, BRANCH, "peasant-del4", status="working", pid=99999)

        result = runner.invoke(ticket_app, ["delete", "del4", "--force"])

        assert result.exit_code == 1
        assert "active peasant" in result.output.lower() or "peasant" in result.output.lower()
        assert path.exists()  # file should NOT have been deleted


class TestRemovedCompatibilityCommands:
    def test_move_has_explicit_branch_destination(self) -> None:
        result = runner.invoke(ticket_app, ["move", "--help"])

        assert result.exit_code == 0
        assert "--to-branch" in unstyle(result.output)

    def test_add_note_is_unregistered(self) -> None:
        result = runner.invoke(ticket_app, ["add-note", "--help"])

        assert result.exit_code == 2
        assert "No such command 'add-note'." in result.output


class TestTicketDefer:
    def test_requires_nonempty_reason_before_moving(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(tickets_dir, "rsn1")

        missing = runner.invoke(ticket_app, ["defer", "rsn1"])
        blank = runner.invoke(ticket_app, ["defer", "rsn1", "--reason", "   "])

        assert missing.exit_code != 0
        assert blank.exit_code == 1
        assert "non-empty" in blank.output
        assert ticket_path.exists()

    def test_batch_preflight_prevents_partial_defer(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        first_path = create_ticket_in(tickets_dir, "first")
        closed_path = tickets_dir / "done1.md"
        write_ticket(
            Ticket(id="done1", status="closed", title="Closed", body="", created=datetime.now(UTC)),
            closed_path,
        )

        result = runner.invoke(
            ticket_app,
            ["defer", "first", "done1", "--reason", "Not this sprint"],
        )

        assert result.exit_code == 1
        assert "closed" in result.output
        assert first_path.exists()
        assert closed_path.exists()
        assert not (backlog_root(cli_project) / "tickets" / first_path.name).exists()

    def test_rejects_archived_ticket(self, cli_project: Path) -> None:
        archive_path = archive_root(cli_project) / "old-feature" / "tickets" / "arch.md"
        write_ticket(
            Ticket(id="arch", status="closed", title="Archived", body="", created=datetime.now(UTC)),
            archive_path,
        )

        result = runner.invoke(ticket_app, ["defer", "arch", "--reason", "Later"])

        assert result.exit_code == 1
        assert "archived" in result.output
        assert archive_path.exists()

    def test_defers_ticket_from_another_live_branch(self, cli_project: Path) -> None:
        other_branch = "feature/other"
        other_dir = ensure_branch_layout(cli_project, other_branch) / "tickets"
        source_path = create_ticket_in(other_dir, "other")

        result = runner.invoke(ticket_app, ["defer", "other", "--reason", "Move to another sprint"])

        assert result.exit_code == 0, result.output
        assert not source_path.exists()
        destination = backlog_root(cli_project) / "tickets" / source_path.name
        assert destination.exists()
        assert f"source: branch:{other_branch.replace('/', '-')}" in read_ticket(destination).body

    def test_rejects_active_peasant(self, cli_project: Path) -> None:
        from kingdom.session import update_agent_state

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(tickets_dir, "peas")
        update_agent_state(cli_project, BRANCH, "peasant-peas", status="working", ticket="peas")

        result = runner.invoke(ticket_app, ["defer", "peas", "--reason", "Later"])

        assert result.exit_code == 1
        assert "active peasant" in result.output
        assert ticket_path.exists()

    def test_rejects_another_execution_context_owner(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(tickets_dir, "owned")

        with patch.dict(os.environ, {"KD_CONTEXT": "other-owner"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "owned"]).exit_code == 0
            owner = resolve_execution_context()
            assert owner is not None
            binding = read_execution_ticket_context(cli_project, owner)

        with patch.dict(os.environ, {"KD_CONTEXT": "caller"}, clear=True):
            result = runner.invoke(ticket_app, ["defer", "owned", "--reason", "Later"])

        assert result.exit_code == 1
        assert "owned by another execution context" in result.output
        assert ticket_path.exists()
        assert read_execution_ticket_context(cli_project, owner) == binding

    def test_defer_resets_and_preserves_ticket_with_lifecycle_history(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        source_path = tickets_dir / "def1.md"
        write_ticket(
            Ticket(
                id="def1",
                status="open",
                title="Deferred ticket",
                body="Original body.\n\n## Worklog\n\n- Existing history",
                deps=["dep1"],
                links=["link1"],
                parent="epic1",
                created=datetime.now(UTC),
            ),
            source_path,
        )

        with patch.dict(os.environ, {"KD_CONTEXT": "ticket-owner"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "def1"]).exit_code == 0
            owner = resolve_execution_context()
            assert owner is not None

        peer = resolve_execution_context(session_id="peer-session", host="hook", cwd=cli_project)
        assert peer is not None
        record_execution_ticket_context(cli_project, peer, "def1", feature=BRANCH)
        with patch.dict(os.environ, {"KD_CONTEXT": "ticket-owner"}, clear=True):
            result = runner.invoke(
                ticket_app,
                ["defer", "def1", "--reason", "Waiting for upstream"],
            )

        assert result.exit_code == 0, result.output
        assert "Deferred def1 to backlog" in result.output
        assert not source_path.exists()
        destination = backlog_root(cli_project) / "tickets" / source_path.name
        ticket = read_ticket(destination)
        assert ticket.status == "open"
        assert ticket.assignee is None
        assert ticket.deps == ["dep1"]
        assert ticket.links == ["link1"]
        assert ticket.parent == "epic1"
        assert "Original body." in ticket.body
        assert "- Existing history" in ticket.body
        assert "## Lifecycle" in ticket.body
        assert owner.context_id in ticket.body
        assert f"source: branch:{BRANCH.replace('/', '-')}" in ticket.body
        assert "previous status: in_progress" in ticket.body
        assert f"previous assignee: {owner.context_id}" in ticket.body
        assert "Waiting for upstream" in ticket.body
        assert read_execution_ticket_context(cli_project, owner) is None
        assert read_execution_ticket_context(cli_project, peer) is None

    def test_already_backlogged_is_idempotent_without_history(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        ticket_path = create_ticket_in(backlog_dir, "later")
        before = ticket_path.read_bytes()

        result = runner.invoke(ticket_app, ["defer", "later", "--reason", "Still later"])

        assert result.exit_code == 0, result.output
        assert "already in backlog" in result.output
        assert ticket_path.read_bytes() == before


class TestTicketPull:
    def test_pull_preserves_markdown_and_relationships_byte_for_byte(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        source_path = backlog_dir / "meta.md"
        source = """---
id: "meta"
status: open
deps: [dep1, dep2]
links: [link1, link2]
created: 2026-08-03T12:00:00Z
type: task
priority: 1
parent: epic
---
# Preserve this ticket

Formatting, links, and relationships must survive exactly.

## Worklog

- Existing history
"""
        source_path.write_text(source)

        result = runner.invoke(ticket_app, ["pull", "meta"])

        assert result.exit_code == 0, result.output
        destination = branch_root(cli_project, BRANCH) / "tickets" / "meta.md"
        assert destination.read_bytes() == source.encode()
        ticket = read_ticket(destination)
        assert ticket.deps == ["dep1", "dep2"]
        assert ticket.links == ["link1", "link2"]
        assert ticket.parent == "epic"

    def test_pull_single_ticket(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "pull")

        result = runner.invoke(ticket_app, ["pull", "pull"])

        assert result.exit_code == 0, result.output
        assert "Pulled pull" in result.output
        assert "Test ticket" in result.output
        # Should be on branch now
        branch_path = branch_root(cli_project, BRANCH) / "tickets" / "pull.md"
        assert branch_path.exists()
        # Should not be in backlog
        assert not (backlog_dir / "pull.md").exists()

    def test_pull_multiple_tickets(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "aa01")
        create_ticket_in(backlog_dir, "bb02")

        result = runner.invoke(ticket_app, ["pull", "aa01", "bb02"])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().split("\n")
        assert len(lines) == 2
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        assert (branch_dir / "aa01.md").exists()
        assert (branch_dir / "bb02.md").exists()

    def test_pull_and_start_binds_only_calling_context(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        workspace_dir = branch_root(cli_project, BRANCH)
        branch_dir = workspace_dir / "tickets"
        peer_path = create_ticket_in(branch_dir, "peer")
        target_path = create_ticket_in(backlog_dir, "bind")
        assert not (workspace_dir / "design.md").exists()

        with patch.dict(os.environ, {"KD_CONTEXT": "peer-session"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "peer"]).exit_code == 0
            peer_context = resolve_execution_context()
            assert peer_context is not None
            peer_binding = read_execution_ticket_context(cli_project, peer_context)

        with patch.dict(os.environ, {"KD_CONTEXT": "pull-session"}, clear=True):
            result = runner.invoke(ticket_app, ["pull", "bind", "--start"])
            pull_context = resolve_execution_context()
            assert pull_context is not None
            pull_binding = read_execution_ticket_context(cli_project, pull_context)

        assert result.exit_code == 0, result.output
        assert "Pulled and started bind" in result.output
        destination = branch_dir / target_path.name
        pulled = read_ticket(destination)
        assert pulled.status == "in_progress"
        assert pulled.assignee == pull_context.context_id
        assert pull_binding is not None
        assert pull_binding["ticket_id"] == "bind"
        assert pull_binding["location"] == f"branch:{BRANCH.replace('/', '-')}"
        assert read_execution_ticket_context(cli_project, peer_context) == peer_binding
        assert read_ticket(peer_path).assignee == peer_context.context_id
        assert not (workspace_dir / "design.md").exists()

    def test_pull_and_start_without_context_does_not_move_ticket(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        source = create_ticket_in(backlog_dir, "noctx")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("os.ttyname", side_effect=OSError),
        ):
            result = runner.invoke(ticket_app, ["pull", "noctx", "--start"])

        assert result.exit_code == 1
        assert "Set KD_CONTEXT" in result.output
        assert source.exists()
        assert not (branch_root(cli_project, BRANCH) / "tickets" / source.name).exists()

    def test_pull_and_start_rejects_multiple_tickets_before_moving(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        first = create_ticket_in(backlog_dir, "one1")
        second = create_ticket_in(backlog_dir, "two2")

        with patch.dict(os.environ, {"KD_CONTEXT": "pull-session"}, clear=True):
            result = runner.invoke(ticket_app, ["pull", "one1", "two2", "--start"])

        assert result.exit_code == 1
        assert "exactly one ticket" in result.output
        assert first.exists()
        assert second.exists()

    def test_pull_ticket_already_selected_reports_precise_conflict(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        branch_path = create_ticket_in(branch_dir, "brnc")

        result = runner.invoke(ticket_app, ["pull", "brnc"])

        assert result.exit_code == 1
        assert "already selected" in result.output
        assert BRANCH.replace("/", "-") in result.output
        assert branch_path.exists()

    def test_pull_in_progress_ticket_does_not_steal_binding(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        source = create_ticket_in(backlog_dir, "busy")

        with patch.dict(os.environ, {"KD_CONTEXT": "owner-session"}, clear=True):
            assert runner.invoke(ticket_app, ["start", "busy"]).exit_code == 0
            owner_context = resolve_execution_context()
            assert owner_context is not None
            owner_binding = read_execution_ticket_context(cli_project, owner_context)

        with patch.dict(os.environ, {"KD_CONTEXT": "pull-session"}, clear=True):
            result = runner.invoke(ticket_app, ["pull", "busy", "--start"])

        assert result.exit_code == 1
        assert "already in progress" in result.output
        assert source.exists()
        assert read_execution_ticket_context(cli_project, owner_context) == owner_binding
        assert read_ticket(source).assignee == owner_context.context_id

    def test_pull_not_found_errors(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["pull", "nope"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_pull_no_ids_errors(self, cli_project: Path) -> None:
        """Invoking `kd tk pull` with no IDs must fail, not silently succeed."""
        result = runner.invoke(ticket_app, ["pull"])

        assert result.exit_code != 0
        assert "TICKET_IDS" in result.output or "at least one ticket ID" in result.output

    def test_pull_no_active_run_errors(self) -> None:
        """Pull without an active run should error."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            # Don't call setup_project — no active run

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "norun")

            result = runner.invoke(ticket_app, ["pull", "norun"])

            assert result.exit_code == 1
            assert "No active session." in result.output

    def test_pull_all_flag_is_not_supported(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["pull", "--all"])

        assert result.exit_code != 0
        assert "No such option" in result.output

    def test_pull_partial_failure_no_moves(self, cli_project: Path) -> None:
        """If second ticket fails validation, first should NOT have moved."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "good")
        # bad doesn't exist — will fail on second ID

        result = runner.invoke(ticket_app, ["pull", "good", "bad"])

        assert result.exit_code == 1
        # good should NOT have been moved (two-pass validation)
        assert (backlog_dir / "good.md").exists()

    def test_pull_duplicate_ids_deduplicates(self, cli_project: Path) -> None:
        """Duplicate IDs in one pull command should move only once."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "dupe")

        result = runner.invoke(ticket_app, ["pull", "dupe", "dupe"])

        assert result.exit_code == 0, result.output
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) == 1

        branch_path = branch_root(cli_project, BRANCH) / "tickets" / "dupe.md"
        assert branch_path.exists()
        assert not (backlog_dir / "dupe.md").exists()

    def test_pull_already_on_branch_errors(self, cli_project: Path) -> None:
        """A destination conflict is caught before other tickets move."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        first = create_ticket_in(backlog_dir, "first")
        duplicate = create_ticket_in(backlog_dir, "here")
        create_ticket_in(branch_dir, "here")

        result = runner.invoke(ticket_app, ["pull", "first", "here"])

        assert result.exit_code == 1
        assert "already selected" in result.output
        assert first.exists()
        assert duplicate.exists()
        assert (branch_dir / "here.md").exists()

    def test_pull_help_describes_backlog_work_selection(self) -> None:
        result = runner.invoke(ticket_app, ["pull", "--help"])
        output = unstyle(result.output)

        assert result.exit_code == 0, result.output
        assert "Select backlog tickets for work" in output
        assert "--start" in output

    def test_pull_ticket_appears_in_ready(self, cli_project: Path) -> None:
        """After pulling, the ticket should appear in `tk ready`."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "rdy1")

        # Pull it
        result = runner.invoke(ticket_app, ["pull", "rdy1"])
        assert result.exit_code == 0, result.output

        # Now check tk ready
        result = runner.invoke(ticket_app, ["list", "--ready", "--json"])
        assert result.exit_code == 0, result.output
        assert "rdy1" in result.output


class TestTicketFind:
    def test_find_branch_ticket_prints_absolute_path(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket_path = create_ticket_in(tickets_dir, "find")

        result = runner.invoke(ticket_app, ["find", "find"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == str(ticket_path.resolve())

    def test_find_backlog_ticket_prints_absolute_path(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        ticket_path = create_ticket_in(backlog_dir, "back")

        result = runner.invoke(ticket_app, ["find", "back"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == str(ticket_path.resolve())

    def test_find_archived_closed_ticket_prints_absolute_path(self, cli_project: Path) -> None:
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        ticket_path = create_ticket_in(archive_dir, "done")
        ticket = read_ticket(ticket_path)
        ticket.status = "closed"
        write_ticket(ticket, ticket_path)

        result = runner.invoke(ticket_app, ["find", "done"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == str(ticket_path.resolve())

    def test_find_not_found_errors(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["find", "nope"])

        assert result.exit_code == 1
        assert "Ticket not found" in result.output
        assert "nope" in result.output

    def test_find_from_parallel_worktree_without_kd(self, tmp_path: Path) -> None:
        main = tmp_path / "kingdom"
        parallel = tmp_path / "kingdom-fixes"
        main.mkdir()
        parallel.mkdir()
        (parallel / ".git").write_text("gitdir: ../kingdom/.git/worktrees/kingdom-fixes\n", encoding="utf-8")
        ensure_branch_layout(main, BRANCH)
        ticket_path = create_ticket_in(branch_root(main, BRANCH) / "tickets", "wt")

        def fake_run(cmd, **kwargs):
            if cmd == ["git", "rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{parallel}\n", stderr="")
            if cmd == ["git", "worktree", "list", "--porcelain"]:
                output = f"worktree {main}\nHEAD abc\n\nworktree {parallel}\nHEAD def\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")
            if cmd == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{BRANCH}\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        with (
            patch("kingdom.state.Path.cwd", return_value=parallel),
            patch("kingdom.state.subprocess.run", side_effect=fake_run),
        ):
            result = runner.invoke(ticket_app, ["find", "wt"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == str(ticket_path.resolve())


class TestTicketParent:
    def test_set_parent(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="epic1", status="open", title="Epic", body="", created=datetime.now(UTC)),
            tickets_dir / "epic1.md",
        )
        write_ticket(
            Ticket(id="child1", status="open", title="Child", body="", created=datetime.now(UTC)),
            tickets_dir / "child1.md",
        )

        result = runner.invoke(ticket_app, ["parent", "child1", "epic1"])
        assert result.exit_code == 0
        assert "parent set to epic1" in result.output

        child = read_ticket(tickets_dir / "child1.md")
        assert child.parent == "epic1"

    def test_clear_parent(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="child2", status="open", title="Child", body="", parent="epic1", created=datetime.now(UTC)),
            tickets_dir / "child2.md",
        )

        result = runner.invoke(ticket_app, ["parent", "child2", "--clear"])
        assert result.exit_code == 0
        assert "parent cleared (was epic1)" in result.output

        child = read_ticket(tickets_dir / "child2.md")
        assert child.parent is None

    def test_reparent(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="epic-a", status="open", title="Epic A", body="", created=datetime.now(UTC)),
            tickets_dir / "epic-a.md",
        )
        write_ticket(
            Ticket(id="epic-b", status="open", title="Epic B", body="", created=datetime.now(UTC)),
            tickets_dir / "epic-b.md",
        )
        write_ticket(
            Ticket(id="child3", status="open", title="Child", body="", parent="epic-a", created=datetime.now(UTC)),
            tickets_dir / "child3.md",
        )

        result = runner.invoke(ticket_app, ["parent", "child3", "epic-b"])
        assert result.exit_code == 0
        assert "epic-a" in result.output
        assert "epic-b" in result.output

        child = read_ticket(tickets_dir / "child3.md")
        assert child.parent == "epic-b"

    def test_no_args_errors(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="child4", status="open", title="Child", body="", created=datetime.now(UTC)),
            tickets_dir / "child4.md",
        )

        result = runner.invoke(ticket_app, ["parent", "child4"])
        assert result.exit_code == 1

    def test_self_parent_errors(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="self1", status="open", title="Self", body="", created=datetime.now(UTC)),
            tickets_dir / "self1.md",
        )

        result = runner.invoke(ticket_app, ["parent", "self1", "self1"])
        assert result.exit_code == 1
        assert "cannot be its own parent" in result.output

    def test_set_and_clear_conflict_errors(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="child5", status="open", title="Child", body="", created=datetime.now(UTC)),
            tickets_dir / "child5.md",
        )

        result = runner.invoke(ticket_app, ["parent", "child5", "epic1", "--clear"])
        assert result.exit_code == 1
