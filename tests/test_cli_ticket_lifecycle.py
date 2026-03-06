"""Tests for ticket lifecycle commands: create, close, reopen, delete, move, pull, add-note."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    ensure_branch_layout,
)
from kingdom.ticket import Ticket, find_ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


def create_ticket_in(directory: Path, ticket_id: str = "kin-t001") -> Path:
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
            ["create", "Typed ticket", "-d", "Body from flag", "-t", "bug"],
        )

        assert result.exit_code == 0, result.output
        # Extract ticket ID from "Created <id>: <title>"
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        created_ticket, _ = found
        assert created_ticket.body == "Body from flag\n\n## Acceptance Criteria\n\n- [ ]"
        assert created_ticket.type == "bug"

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
        created_ticket, _ = found
        assert created_ticket.priority == 1

    def test_create_no_trailing_whitespace(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Whitespace check"])

        assert result.exit_code == 0
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        _, ticket_path = found
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
        path = create_ticket_in(backlog_dir, "kin-arch")

        result = runner.invoke(ticket_app, ["close", "kin-arch"])

        assert result.exit_code == 0, result.output
        assert "closed" in result.output
        # Should have moved to archive
        assert not path.exists()
        archived = archive_root(cli_project) / "backlog" / "tickets" / "kin-arch.md"
        assert archived.exists()

    def test_close_branch_ticket_stays_in_place(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-stay")

        result = runner.invoke(ticket_app, ["close", "kin-stay"])

        assert result.exit_code == 0, result.output
        # Should still be in the branch
        assert path.exists()

    def test_reopen_archived_backlog_ticket_restores(self, cli_project: Path) -> None:
        # Create a closed ticket directly in archive
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ticket = Ticket(
            id="kin-rest",
            status="closed",
            title="Archived ticket",
            body="Body",
            created=datetime.now(UTC),
        )
        archived_path = archive_dir / "kin-rest.md"
        write_ticket(ticket, archived_path)

        result = runner.invoke(ticket_app, ["reopen", "kin-rest"])

        assert result.exit_code == 0, result.output
        # Should have moved back to backlog
        assert not archived_path.exists()
        restored = backlog_root(cli_project) / "tickets" / "kin-rest.md"
        assert restored.exists()

    def test_start_archived_backlog_ticket_restores(self, cli_project: Path) -> None:
        # Create a closed ticket in archive
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ticket = Ticket(
            id="kin-strt",
            status="closed",
            title="Start me",
            body="Body",
            created=datetime.now(UTC),
        )
        archived_path = archive_dir / "kin-strt.md"
        write_ticket(ticket, archived_path)

        result = runner.invoke(ticket_app, ["start", "kin-strt"])

        assert result.exit_code == 0, result.output
        assert not archived_path.exists()
        restored = backlog_root(cli_project) / "tickets" / "kin-strt.md"
        assert restored.exists()


class TestTicketStatus:
    def test_status_sets_arbitrary_value(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-stat")

        result = runner.invoke(ticket_app, ["status", "kin-stat", "blocked"])

        assert result.exit_code == 0, result.output
        assert "open → blocked" in result.output
        ticket = read_ticket(branch_dir / "kin-stat.md")
        assert ticket.status == "blocked"

    def test_status_round_trip(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-rt")

        runner.invoke(ticket_app, ["status", "kin-rt", "in_review"])
        result = runner.invoke(ticket_app, ["status", "kin-rt", "waiting"])

        assert result.exit_code == 0, result.output
        assert "in_review → waiting" in result.output


class TestTicketCloseIdempotent:
    def test_close_already_archived_ticket_is_noop(self, cli_project: Path) -> None:
        """Closing an already-closed archived ticket should not double-move."""
        # Create a closed ticket directly in archive
        archive_dir = archive_root(cli_project) / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ticket = Ticket(
            id="kin-idem",
            status="closed",
            title="Already archived",
            body="Body",
            created=datetime.now(UTC),
        )
        archived_path = archive_dir / "kin-idem.md"
        write_ticket(ticket, archived_path)

        result = runner.invoke(ticket_app, ["close", "kin-idem"])

        assert result.exit_code == 0, result.output
        # Should still be in archive, not moved elsewhere
        assert archived_path.exists()
        # Should NOT be in backlog
        assert not (backlog_root(cli_project) / "tickets" / "kin-idem.md").exists()


class TestTicketCloseReason:
    def test_close_with_reason_appends_worklog(self, cli_project: Path) -> None:
        """Closing with --reason should add a worklog entry."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-reas")

        result = runner.invoke(ticket_app, ["close", "kin-reas", "-m", "No longer needed"])

        assert result.exit_code == 0, result.output
        assert "closed" in result.output
        content = path.read_text()
        assert "## Worklog" in content
        assert "Closed: No longer needed" in content

    def test_close_with_long_reason_flag(self, cli_project: Path) -> None:
        """--reason should also work (long form of -m)."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-rsnl")

        result = runner.invoke(ticket_app, ["close", "kin-rsnl", "--reason", "Duplicate of kin-xyz"])

        assert result.exit_code == 0, result.output
        content = path.read_text()
        assert "Closed: Duplicate of kin-xyz" in content

    def test_close_without_reason_no_worklog(self, cli_project: Path) -> None:
        """Closing without --reason should not add a worklog entry."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-nors")

        result = runner.invoke(ticket_app, ["close", "kin-nors"])

        assert result.exit_code == 0, result.output
        content = path.read_text()
        assert "## Worklog" not in content


class TestTicketCloseDuplicate:
    def test_duplicate_of_sets_field_and_closes(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-dup1")
        create_ticket_in(branch_dir, "kin-orig")

        result = runner.invoke(ticket_app, ["close", "kin-dup1", "--duplicate-of", "kin-orig"])

        assert result.exit_code == 0, result.output
        assert "closed" in result.output
        ticket = read_ticket(branch_dir / "kin-dup1.md")
        assert ticket.status == "closed"
        assert ticket.duplicate_of == "kin-orig"

    def test_duplicate_of_adds_worklog(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-dup2")
        create_ticket_in(branch_dir, "kin-xyz")

        runner.invoke(ticket_app, ["close", "kin-dup2", "--duplicate-of", "kin-xyz"])

        content = path.read_text()
        assert "Closed: Duplicate of kin-xyz" in content

    def test_duplicate_of_with_custom_reason(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-dup3")
        create_ticket_in(branch_dir, "kin-xyz")

        runner.invoke(ticket_app, ["close", "kin-dup3", "--duplicate-of", "kin-xyz", "-m", "Merged into kin-xyz"])

        content = path.read_text()
        assert "Closed: Merged into kin-xyz" in content

    def test_duplicate_of_serialized_in_frontmatter(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-dup4")
        create_ticket_in(branch_dir, "kin-orig")

        runner.invoke(ticket_app, ["close", "kin-dup4", "--duplicate-of", "kin-orig"])

        content = (branch_dir / "kin-dup4.md").read_text()
        assert "duplicate-of: kin-orig" in content


class TestTicketCloseDuplicateValidation:
    def test_duplicate_of_rejects_nonexistent_target(self, cli_project: Path) -> None:
        """--duplicate-of should fail if the target ticket doesn't exist."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-dup1")

        result = runner.invoke(ticket_app, ["close", "kin-dup1", "--duplicate-of", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "nonexistent" in result.output.lower()
        # Ticket should NOT be closed
        ticket = read_ticket(branch_dir / "kin-dup1.md")
        assert ticket.status != "closed"

    def test_duplicate_of_rejects_self_reference(self, cli_project: Path) -> None:
        """--duplicate-of should fail if the target is the same ticket."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-self")

        result = runner.invoke(ticket_app, ["close", "kin-self", "--duplicate-of", "kin-self"])

        assert result.exit_code == 1
        assert "itself" in result.output.lower() or "self" in result.output.lower()
        ticket = read_ticket(branch_dir / "kin-self.md")
        assert ticket.status != "closed"

    def test_duplicate_of_stores_canonical_id(self, cli_project: Path) -> None:
        """--duplicate-of should resolve and store the full canonical ticket ID."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-dup5")
        create_ticket_in(branch_dir, "kin-target")

        # Use partial ID
        result = runner.invoke(ticket_app, ["close", "kin-dup5", "--duplicate-of", "kin-target"])

        assert result.exit_code == 0, result.output
        ticket = read_ticket(branch_dir / "kin-dup5.md")
        assert ticket.duplicate_of == "kin-target"


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
        from kingdom.session import AgentState, set_agent_state

        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-pwrn")

        # Create an active peasant session for this ticket
        state = AgentState(name="peasant-kin-pwrn", status="working", ticket="kin-pwrn")
        set_agent_state(cli_project, BRANCH, "peasant-kin-pwrn", state)

        result = runner.invoke(ticket_app, ["close", "kin-pwrn"])

        assert result.exit_code == 0
        assert "closed" in result.output
        assert "Warning" in result.output
        assert "peasant-kin-pwrn" in result.output

    def test_no_warning_when_no_peasant(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-nop")

        result = runner.invoke(ticket_app, ["close", "kin-nop"])

        assert result.exit_code == 0
        assert "closed" in result.output
        assert "Warning" not in result.output

    def test_no_warning_for_stopped_peasant(self, cli_project: Path) -> None:
        from kingdom.session import AgentState, set_agent_state

        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-stp")

        state = AgentState(name="peasant-kin-stp", status="stopped", ticket="kin-stp")
        set_agent_state(cli_project, BRANCH, "peasant-kin-stp", state)

        result = runner.invoke(ticket_app, ["close", "kin-stp"])

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
        path = create_ticket_in(branch_dir, "kin-del1")

        result = runner.invoke(ticket_app, ["delete", "kin-del1", "--force"])

        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output
        assert "kin-del1" in result.output
        assert not path.exists()

    def test_delete_not_found(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["delete", "nope", "--force"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_delete_cancelled(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-del2")

        result = runner.invoke(ticket_app, ["delete", "kin-del2"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        assert path.exists()

    def test_delete_confirmed(self, cli_project: Path) -> None:
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-del3")

        result = runner.invoke(ticket_app, ["delete", "kin-del3"], input="y\n")

        assert result.exit_code == 0, result.output
        assert "Deleted" in result.output
        assert not path.exists()

    def test_delete_blocked_by_active_peasant(self, cli_project: Path) -> None:
        from kingdom.session import AgentState, set_agent_state

        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        path = create_ticket_in(branch_dir, "kin-del4")

        set_agent_state(
            cli_project,
            BRANCH,
            "peasant-kin-del4",
            AgentState(name="peasant-kin-del4", status="working", pid=99999),
        )

        result = runner.invoke(ticket_app, ["delete", "kin-del4", "--force"])

        assert result.exit_code == 1
        assert "active peasant" in result.output.lower() or "peasant" in result.output.lower()
        assert path.exists()  # file should NOT have been deleted


class TestTicketMove:
    def test_move_defaults_to_current_branch(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-mv01")

        result = runner.invoke(ticket_app, ["move", "kin-mv01"])

        assert result.exit_code == 0, result.output
        assert "Moved" in result.output
        assert "branch 'feature-ticket-test'" in result.output
        branch_tickets = branch_root(cli_project, BRANCH) / "tickets" / "kin-mv01.md"
        assert branch_tickets.exists()
        # Source must be removed (no duplicate in backlog)
        assert not (backlog_dir / "kin-mv01.md").exists()

    def test_move_to_backlog_shows_backlog_label(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-mv04")

        result = runner.invoke(ticket_app, ["move", "kin-mv04", "--to", "backlog"])

        assert result.exit_code == 0, result.output
        assert "Moved kin-mv04 to backlog" in result.output
        # Verify actual file state, not just CLI output
        assert not (tickets_dir / "kin-mv04.md").exists(), "Source ticket should be removed"
        assert (backlog_root(cli_project) / "tickets" / "kin-mv04.md").exists(), "Ticket should exist in backlog"

    def test_move_already_in_destination(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-mv02")

        result = runner.invoke(ticket_app, ["move", "kin-mv02"])

        assert result.exit_code == 0, result.output
        assert "already in branch 'feature-ticket-test'" in result.output

    def test_move_no_active_branch_errors(self) -> None:
        """Move without an active branch should error with guidance."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH)
            # Don't set current run
            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-mv03")

            result = runner.invoke(ticket_app, ["move", "kin-mv03"])

            assert result.exit_code == 1
            assert "No current branch active" in result.output
            assert "kd start" in result.output

    def test_move_to_branch_resolves_current_branch(self, cli_project: Path) -> None:
        """--to branch should resolve to the current branch, not literal 'branch'."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-mv05")

        result = runner.invoke(ticket_app, ["move", "kin-mv05", "--to", "branch"])

        assert result.exit_code == 0, result.output
        assert "Moved" in result.output
        assert f"branch '{BRANCH}'" in result.output
        branch_tickets = branch_root(cli_project, BRANCH) / "tickets" / "kin-mv05.md"
        assert branch_tickets.exists()
        assert not (backlog_dir / "kin-mv05.md").exists()

    def test_move_to_nonexistent_branch_errors(self) -> None:
        """--to with a branch that doesn't exist in .kd/branches/ errors."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH)
            from kingdom.state import set_current_run

            set_current_run(base, BRANCH)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv06")

            result = runner.invoke(ticket_app, ["move", "kin-mv06", "--to", "feature/nope"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_move_across_branches(self) -> None:
        """kd tk move <id> --to <branch> moves ticket between branches."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH)
            ensure_branch_layout(base, "feature/other")
            from kingdom.state import set_current_run

            set_current_run(base, BRANCH)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv07")

            result = runner.invoke(ticket_app, ["move", "kin-mv07", "--to", "feature/other"])

            assert result.exit_code == 0, result.output
            assert "Moved" in result.output
            # Verify file moved
            assert not (tickets_dir / "kin-mv07.md").exists()
            assert (branch_root(base, "feature/other") / "tickets" / "kin-mv07.md").exists()

    def test_move_blocked_by_active_peasant(self) -> None:
        """Moving a ticket with an active peasant is blocked."""
        from kingdom.session import AgentState, set_agent_state
        from kingdom.state import set_current_run

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH)
            ensure_branch_layout(base, "feature/other")
            set_current_run(base, BRANCH)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv08")

            # Create an active peasant session for this ticket
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-mv08",
                AgentState(name="peasant-kin-mv08", status="working", ticket="kin-mv08"),
            )

            result = runner.invoke(ticket_app, ["move", "kin-mv08", "--to", "feature/other"])

            assert result.exit_code == 1
            assert "active peasant" in result.output

    def test_move_allowed_after_done_peasant(self) -> None:
        """Moving a ticket whose peasant is done/failed/stopped should succeed."""
        from kingdom.session import AgentState, set_agent_state
        from kingdom.state import set_current_run

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH)
            ensure_branch_layout(base, "feature/other")
            set_current_run(base, BRANCH)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv09")

            # Peasant finished — terminal status should not block the move
            set_agent_state(
                base,
                BRANCH,
                "peasant-kin-mv09",
                AgentState(name="peasant-kin-mv09", status="done", ticket="kin-mv09"),
            )

            result = runner.invoke(ticket_app, ["move", "kin-mv09", "--to", "feature/other"])

            assert result.exit_code == 0, result.output
            assert "Moved" in result.output
            assert not (tickets_dir / "kin-mv09.md").exists()
            assert (branch_root(base, "feature/other") / "tickets" / "kin-mv09.md").exists()


class TestTicketPull:
    def test_pull_single_ticket(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-pull")

        result = runner.invoke(ticket_app, ["pull", "kin-pull"])

        assert result.exit_code == 0, result.output
        assert "Pulled kin-pull" in result.output
        assert "Test ticket" in result.output
        # Should be on branch now
        branch_path = branch_root(cli_project, BRANCH) / "tickets" / "kin-pull.md"
        assert branch_path.exists()
        # Should not be in backlog
        assert not (backlog_dir / "kin-pull.md").exists()

    def test_pull_multiple_tickets(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-aa01")
        create_ticket_in(backlog_dir, "kin-bb02")

        result = runner.invoke(ticket_app, ["pull", "kin-aa01", "kin-bb02"])

        assert result.exit_code == 0, result.output
        lines = result.output.strip().split("\n")
        assert len(lines) == 2
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        assert (branch_dir / "kin-aa01.md").exists()
        assert (branch_dir / "kin-bb02.md").exists()

    def test_pull_not_in_backlog_errors(self, cli_project: Path) -> None:
        # Create ticket on branch, not backlog
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-brnc")

        result = runner.invoke(ticket_app, ["pull", "kin-brnc"])

        assert result.exit_code == 1
        assert "not found in backlog" in result.output

    def test_pull_not_found_errors(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["pull", "kin-nope"])

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
            create_ticket_in(backlog_dir, "kin-norun")

            result = runner.invoke(ticket_app, ["pull", "kin-norun"])

            assert result.exit_code == 1
            assert "No active session." in result.output

    def test_pull_all_flag_is_not_supported(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["pull", "--all"])

        assert result.exit_code != 0
        assert "No such option" in result.output

    def test_pull_partial_failure_no_moves(self, cli_project: Path) -> None:
        """If second ticket fails validation, first should NOT have moved."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-good")
        # kin-bad doesn't exist — will fail on second ID

        result = runner.invoke(ticket_app, ["pull", "kin-good", "kin-bad"])

        assert result.exit_code == 1
        # kin-good should NOT have been moved (two-pass validation)
        assert (backlog_dir / "kin-good.md").exists()

    def test_pull_duplicate_ids_deduplicates(self, cli_project: Path) -> None:
        """Duplicate IDs in one pull command should move only once."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-dupe")

        result = runner.invoke(ticket_app, ["pull", "kin-dupe", "kin-dupe"])

        assert result.exit_code == 0, result.output
        lines = [line for line in result.stdout.strip().split("\n") if line]
        assert len(lines) == 1

        branch_path = branch_root(cli_project, BRANCH) / "tickets" / "kin-dupe.md"
        assert branch_path.exists()
        assert not (backlog_dir / "kin-dupe.md").exists()

    def test_pull_already_on_branch_errors(self, cli_project: Path) -> None:
        """Pulling a ticket that's already on the current branch should error."""
        branch_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(branch_dir, "kin-here")

        result = runner.invoke(ticket_app, ["pull", "kin-here"])

        assert result.exit_code == 1
        assert "not found in backlog" in result.output
        # Ticket should still be on the branch
        assert (branch_dir / "kin-here.md").exists()

    def test_pull_ticket_appears_in_ready(self, cli_project: Path) -> None:
        """After pulling, the ticket should appear in `tk ready`."""
        backlog_dir = backlog_root(cli_project) / "tickets"
        create_ticket_in(backlog_dir, "kin-rdy1")

        # Pull it
        result = runner.invoke(ticket_app, ["pull", "kin-rdy1"])
        assert result.exit_code == 0, result.output

        # Now check tk ready
        result = runner.invoke(ticket_app, ["list", "--ready", "--json"])
        assert result.exit_code == 0, result.output
        assert "kin-rdy1" in result.output


class TestTicketAddNote:
    """Tests for kd tk add-note."""

    def test_adds_note_to_ticket(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Test", body="Body.", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        result = runner.invoke(ticket_app, ["add-note", "aaaa", "This is a note"])
        assert result.exit_code == 0
        assert "note added" in result.output

        content = (tickets_dir / "aaaa.md").read_text()
        assert "This is a note" in content
        assert "**Note (" in content
