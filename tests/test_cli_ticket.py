"""Tests for the ticket CLI commands (create, close, reopen, pull)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.cli import format_ticket_summary
from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    ensure_branch_layout,
    ensure_run_layout,
    set_current_run,
)
from kingdom.ticket import Ticket, find_ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


def setup_project(base: Path) -> None:
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


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
    def test_create_echoes_id_and_title(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "My new ticket"])

            assert result.exit_code == 0, result.output
            output = result.output.strip()
            assert output.startswith("Created ")
            assert "My new ticket" in output

    def test_create_backlog_echoes_id_and_title(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Backlog ticket", "--backlog"])

            assert result.exit_code == 0, result.output
            output = result.output.strip()
            assert output.startswith("Created ")
            assert "(backlog)" in output
            assert "Backlog ticket" in output

    def test_create_non_backlog_omits_backlog_label(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Branch ticket"])

            assert result.exit_code == 0, result.output
            output = result.output.strip()
            assert output.startswith("Created ")
            assert "(backlog)" not in output

    def test_create_accepts_description_and_type_flags(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(
                cli.app,
                ["tk", "create", "Typed ticket", "-d", "Body from flag", "-t", "bug"],
            )

            assert result.exit_code == 0, result.output
            # Extract ticket ID from "Created <id>: <title>"
            ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
            found = find_ticket(base, ticket_id)
            assert found is not None
            created_ticket, _ = found
            assert created_ticket.body == "Body from flag"
            assert created_ticket.type == "bug"

    def test_create_out_of_range_priority_clamps(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Bad priority", "-p", "5"])

            assert result.exit_code == 0
            output = result.output.strip()
            assert output.startswith("Created ")

            # Warning should be on stderr so stdout stays script-friendly.
            assert "Warning: Priority 5 outside valid range" in result.stderr
            assert "Warning: Priority 5 outside valid range" not in result.stdout

            ticket_id = output.split(":")[0].replace("Created ", "")
            found = find_ticket(base, ticket_id)
            assert found is not None
            created_ticket, _ = found
            assert created_ticket.priority == 3

    def test_create_no_trailing_whitespace(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Whitespace check"])

            assert result.exit_code == 0
            ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
            found = find_ticket(base, ticket_id)
            assert found is not None
            _, ticket_path = found
            content = ticket_path.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                assert line == line.rstrip(), f"Line {i} has trailing whitespace: {line!r}"

    def test_create_prints_file_path(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Path ticket"])

            assert result.exit_code == 0, result.output
            lines = result.output.strip().splitlines()
            assert len(lines) == 2
            # First line is the "Created <id>: <title>" message
            assert lines[0].startswith("Created ")
            # Second line is the file path
            assert lines[1].endswith(".md")
            assert Path(lines[1]).exists()

    def test_create_backlog_prints_file_path(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Backlog path ticket", "--backlog"])

            assert result.exit_code == 0, result.output
            lines = result.output.strip().splitlines()
            assert len(lines) == 2
            assert lines[1].endswith(".md")
            assert "backlog" in lines[1]
            assert Path(lines[1]).exists()


class TestTicketCloseArchive:
    def test_close_backlog_ticket_archives(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            backlog_dir = backlog_root(base) / "tickets"
            path = create_ticket_in(backlog_dir, "kin-arch")

            result = runner.invoke(cli.app, ["tk", "close", "kin-arch"])

            assert result.exit_code == 0, result.output
            assert "closed" in result.output
            # Should have moved to archive
            assert not path.exists()
            archived = archive_root(base) / "backlog" / "tickets" / "kin-arch.md"
            assert archived.exists()

    def test_close_branch_ticket_stays_in_place(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-stay")

            result = runner.invoke(cli.app, ["tk", "close", "kin-stay"])

            assert result.exit_code == 0, result.output
            # Should still be in the branch
            assert path.exists()

    def test_reopen_archived_backlog_ticket_restores(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create a closed ticket directly in archive
            archive_dir = archive_root(base) / "backlog" / "tickets"
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

            result = runner.invoke(cli.app, ["tk", "reopen", "kin-rest"])

            assert result.exit_code == 0, result.output
            # Should have moved back to backlog
            assert not archived_path.exists()
            restored = backlog_root(base) / "tickets" / "kin-rest.md"
            assert restored.exists()

    def test_start_archived_backlog_ticket_restores(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create a closed ticket in archive
            archive_dir = archive_root(base) / "backlog" / "tickets"
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

            result = runner.invoke(cli.app, ["tk", "start", "kin-strt"])

            assert result.exit_code == 0, result.output
            assert not archived_path.exists()
            restored = backlog_root(base) / "tickets" / "kin-strt.md"
            assert restored.exists()


class TestTicketPull:
    def test_pull_single_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-pull")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-pull"])

            assert result.exit_code == 0, result.output
            assert "Pulled kin-pull" in result.output
            assert "Test ticket" in result.output
            # Should be on branch now
            branch_path = branch_root(base, BRANCH) / "tickets" / "kin-pull.md"
            assert branch_path.exists()
            # Should not be in backlog
            assert not (backlog_dir / "kin-pull.md").exists()

    def test_pull_multiple_tickets(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-aa01")
            create_ticket_in(backlog_dir, "kin-bb02")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-aa01", "kin-bb02"])

            assert result.exit_code == 0, result.output
            lines = result.output.strip().split("\n")
            assert len(lines) == 2
            branch_dir = branch_root(base, BRANCH) / "tickets"
            assert (branch_dir / "kin-aa01.md").exists()
            assert (branch_dir / "kin-bb02.md").exists()

    def test_pull_not_in_backlog_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create ticket on branch, not backlog
            branch_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(branch_dir, "kin-brnc")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-brnc"])

            assert result.exit_code == 1
            assert "not found in backlog" in result.output

    def test_pull_not_found_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "pull", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_pull_no_ids_errors(self) -> None:
        """Invoking `kd tk pull` with no IDs must fail, not silently succeed."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "pull"])

            assert result.exit_code != 0
            assert "TICKET_IDS" in result.output or "at least one ticket ID" in result.output

    def test_pull_no_active_run_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            # Don't call setup_project — no active run

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-norun")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-norun"])

            assert result.exit_code == 1
            assert "No active session." in result.output

    def test_pull_all_flag_is_not_supported(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "pull", "--all"])

            assert result.exit_code != 0
            assert "No such option" in result.output

    def test_pull_partial_failure_no_moves(self) -> None:
        """If second ticket fails validation, first should NOT have moved."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-good")
            # kin-bad doesn't exist — will fail on second ID

            result = runner.invoke(cli.app, ["tk", "pull", "kin-good", "kin-bad"])

            assert result.exit_code == 1
            # kin-good should NOT have been moved (two-pass validation)
            assert (backlog_dir / "kin-good.md").exists()

    def test_pull_duplicate_ids_deduplicates(self) -> None:
        """Duplicate IDs in one pull command should move only once."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-dupe")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-dupe", "kin-dupe"])

            assert result.exit_code == 0, result.output
            lines = [line for line in result.stdout.strip().split("\n") if line]
            assert len(lines) == 1

            branch_path = branch_root(base, BRANCH) / "tickets" / "kin-dupe.md"
            assert branch_path.exists()
            assert not (backlog_dir / "kin-dupe.md").exists()

    def test_pull_legacy_run_moves_into_legacy_tickets_dir(self) -> None:
        """With a legacy active run, pull should target .kd/runs/<run>/tickets."""
        with runner.isolated_filesystem():
            base = Path.cwd()

            legacy_run = "legacy-feature"
            ensure_run_layout(base, legacy_run)
            set_current_run(base, legacy_run)

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-legacy")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-legacy"])

            assert result.exit_code == 0, result.output
            legacy_ticket_path = base / ".kd" / "runs" / legacy_run / "tickets" / "kin-legacy.md"
            assert legacy_ticket_path.exists()
            assert "Pulled kin-legacy" in result.output

    def test_pull_already_on_branch_errors(self) -> None:
        """Pulling a ticket that's already on the current branch should error."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            branch_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(branch_dir, "kin-here")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-here"])

            assert result.exit_code == 1
            assert "not found in backlog" in result.output
            # Ticket should still be on the branch
            assert (branch_dir / "kin-here.md").exists()

    def test_pull_ticket_appears_in_ready(self) -> None:
        """After pulling, the ticket should appear in `tk ready`."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-rdy1")

            # Pull it
            result = runner.invoke(cli.app, ["tk", "pull", "kin-rdy1"])
            assert result.exit_code == 0, result.output

            # Now check tk ready
            result = runner.invoke(cli.app, ["tk", "ready", "--json"])
            assert result.exit_code == 0, result.output
            assert "kin-rdy1" in result.output


class TestTicketCloseIdempotent:
    def test_close_already_archived_ticket_is_noop(self) -> None:
        """Closing an already-closed archived ticket should not double-move."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            # Create a closed ticket directly in archive
            archive_dir = archive_root(base) / "backlog" / "tickets"
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

            result = runner.invoke(cli.app, ["tk", "close", "kin-idem"])

            assert result.exit_code == 0, result.output
            # Should still be in archive, not moved elsewhere
            assert archived_path.exists()
            # Should NOT be in backlog
            assert not (backlog_root(base) / "tickets" / "kin-idem.md").exists()


class TestTicketCloseReason:
    def test_close_with_reason_appends_worklog(self) -> None:
        """Closing with --reason should add a worklog entry."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-reas")

            result = runner.invoke(cli.app, ["tk", "close", "kin-reas", "-m", "No longer needed"])

            assert result.exit_code == 0, result.output
            assert "closed" in result.output
            content = path.read_text()
            assert "## Worklog" in content
            assert "Closed: No longer needed" in content

    def test_close_with_long_reason_flag(self) -> None:
        """--reason should also work (long form of -m)."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-rsnl")

            result = runner.invoke(cli.app, ["tk", "close", "kin-rsnl", "--reason", "Duplicate of kin-xyz"])

            assert result.exit_code == 0, result.output
            content = path.read_text()
            assert "Closed: Duplicate of kin-xyz" in content

    def test_close_without_reason_no_worklog(self) -> None:
        """Closing without --reason should not add a worklog entry."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-nors")

            result = runner.invoke(cli.app, ["tk", "close", "kin-nors"])

            assert result.exit_code == 0, result.output
            content = path.read_text()
            assert "## Worklog" not in content


class TestTicketCloseDuplicate:
    def test_duplicate_of_sets_field_and_closes(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(branch_dir, "kin-dup1")
            create_ticket_in(branch_dir, "kin-orig")

            result = runner.invoke(cli.app, ["tk", "close", "kin-dup1", "--duplicate-of", "kin-orig"])

            assert result.exit_code == 0, result.output
            assert "closed" in result.output
            ticket = read_ticket(branch_dir / "kin-dup1.md")
            assert ticket.status == "closed"
            assert ticket.duplicate_of == "kin-orig"

    def test_duplicate_of_adds_worklog(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-dup2")

            runner.invoke(cli.app, ["tk", "close", "kin-dup2", "--duplicate-of", "kin-xyz"])

            content = path.read_text()
            assert "Closed: Duplicate of kin-xyz" in content

    def test_duplicate_of_with_custom_reason(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-dup3")

            runner.invoke(
                cli.app, ["tk", "close", "kin-dup3", "--duplicate-of", "kin-xyz", "-m", "Merged into kin-xyz"]
            )

            content = path.read_text()
            assert "Closed: Merged into kin-xyz" in content

    def test_duplicate_of_serialized_in_frontmatter(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(branch_dir, "kin-dup4")

            runner.invoke(cli.app, ["tk", "close", "kin-dup4", "--duplicate-of", "kin-orig"])

            content = (branch_dir / "kin-dup4.md").read_text()
            assert "duplicate-of: kin-orig" in content


class TestTicketDelete:
    def test_delete_removes_file(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-del1")

            result = runner.invoke(cli.app, ["tk", "delete", "kin-del1", "--force"])

            assert result.exit_code == 0, result.output
            assert "Deleted" in result.output
            assert "kin-del1" in result.output
            assert not path.exists()

    def test_delete_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "delete", "nope", "--force"])

            assert result.exit_code == 1
            assert "not found" in result.output.lower()

    def test_delete_cancelled(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-del2")

            result = runner.invoke(cli.app, ["tk", "delete", "kin-del2"], input="n\n")

            assert result.exit_code == 0
            assert "Cancelled" in result.output
            assert path.exists()

    def test_delete_confirmed(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            branch_dir = branch_root(base, BRANCH) / "tickets"
            path = create_ticket_in(branch_dir, "kin-del3")

            result = runner.invoke(cli.app, ["tk", "delete", "kin-del3"], input="y\n")

            assert result.exit_code == 0, result.output
            assert "Deleted" in result.output
            assert not path.exists()


class TestTicketMove:
    def test_move_defaults_to_current_branch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-mv01")

            result = runner.invoke(cli.app, ["tk", "move", "kin-mv01"])

            assert result.exit_code == 0, result.output
            assert "Moved" in result.output
            assert "branch 'feature-ticket-test'" in result.output
            branch_tickets = branch_root(base, BRANCH) / "tickets" / "kin-mv01.md"
            assert branch_tickets.exists()
            # Source must be removed (no duplicate in backlog)
            assert not (backlog_dir / "kin-mv01.md").exists()

    def test_move_to_backlog_shows_backlog_label(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv04")

            result = runner.invoke(cli.app, ["tk", "move", "kin-mv04", "--to", "backlog"])

            assert result.exit_code == 0, result.output
            assert "Moved kin-mv04 to backlog" in result.output
            # Verify actual file state, not just CLI output
            assert not (tickets_dir / "kin-mv04.md").exists(), "Source ticket should be removed"
            assert (backlog_root(base) / "tickets" / "kin-mv04.md").exists(), "Ticket should exist in backlog"

    def test_move_already_in_destination(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv02")

            result = runner.invoke(cli.app, ["tk", "move", "kin-mv02"])

            assert result.exit_code == 0, result.output
            assert "already in branch 'feature-ticket-test'" in result.output

    def test_move_no_active_branch_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, BRANCH)
            # Don't set current run
            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-mv03")

            result = runner.invoke(cli.app, ["tk", "move", "kin-mv03"])

            assert result.exit_code == 1
            assert "No current branch active" in result.output
            assert "kd start" in result.output


class TestTicketList:
    def test_list_hides_closed_by_default(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            # Create one open and one closed ticket
            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(
                id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(closed_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "Open ticket" in result.output
            assert "Closed ticket" not in result.output

    def test_list_include_closed_shows_all(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(
                id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(closed_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--include-closed"])

            assert result.exit_code == 0
            assert "Open ticket" in result.output
            assert "Closed ticket" in result.output

    def test_list_all_hides_closed_by_default(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(
                id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(closed_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--all"])

            assert result.exit_code == 0
            # Rich table may wrap long titles; check ticket IDs instead
            assert "aaaa" in result.output
            assert "bbbb" not in result.output

    def test_list_status_filter_open(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            in_progress = Ticket(
                id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
            )
            closed_ticket = Ticket(
                id="cccc", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(in_progress, tickets_dir / "bbbb.md")
            write_ticket(closed_ticket, tickets_dir / "cccc.md")

            result = runner.invoke(cli.app, ["tk", "list", "--status", "open"])

            assert result.exit_code == 0
            assert "Open ticket" in result.output
            assert "In-progress ticket" not in result.output
            assert "Closed ticket" not in result.output

    def test_list_status_filter_in_progress(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            in_progress = Ticket(
                id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(in_progress, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--status", "in_progress"])

            assert result.exit_code == 0
            assert "Open ticket" not in result.output
            assert "In-progress ticket" in result.output

    def test_list_status_filter_closed(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(
                id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(closed_ticket, tickets_dir / "bbbb.md")

            # --status closed should show closed tickets even without --include-closed
            result = runner.invoke(cli.app, ["tk", "list", "--status", "closed"])

            assert result.exit_code == 0
            assert "Open ticket" not in result.output
            assert "Closed ticket" in result.output

    def test_list_status_filter_in_review(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            review_ticket = Ticket(
                id="bbbb", status="in_review", title="Review ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(review_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--status", "in_review"])

            assert result.exit_code == 0
            assert "Open ticket" not in result.output
            assert "Review ticket" in result.output

    def test_list_shows_in_review_by_default(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            review_ticket = Ticket(
                id="aaaa", status="in_review", title="Review ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(review_ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "Review ticket" in result.output

    def test_list_status_filter_invalid(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "list", "--status", "bogus"])

            assert result.exit_code == 1
            assert "Invalid status" in result.output

    def test_list_status_filter_with_all(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(
                id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(closed_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--all", "--status", "closed"])

            assert result.exit_code == 0
            # Rich table may wrap long titles; check ticket IDs instead
            assert "aaaa" not in result.output
            assert "bbbb" in result.output

    def test_list_status_filter_short_flag(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            in_progress = Ticket(
                id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(in_progress, tickets_dir / "bbbb.md")

            # Use -s short flag
            result = runner.invoke(cli.app, ["tk", "list", "-s", "open"])

            assert result.exit_code == 0
            assert "Open ticket" in result.output
            assert "In-progress ticket" not in result.output

    def test_list_summary_line_shows_counts(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            ip_ticket = Ticket(
                id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
            )
            closed_ticket = Ticket(
                id="cccc", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(ip_ticket, tickets_dir / "bbbb.md")
            write_ticket(closed_ticket, tickets_dir / "cccc.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            # Summary should show all statuses including closed (even though closed tickets are hidden)
            assert "1 open" in result.output
            assert "1 in_progress" in result.output
            assert "1 closed" in result.output
            assert "3 total" in result.output

    def test_list_summary_line_not_in_json_output(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="A ticket", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list", "--json"])

            assert result.exit_code == 0
            assert "total" not in result.output

    def test_list_summary_with_all_flag(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(
                id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(closed_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--all"])

            assert result.exit_code == 0
            assert "1 open" in result.output
            assert "1 closed" in result.output
            assert "2 total" in result.output

    def test_list_no_tickets_shows_no_summary(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "total" not in result.output


class TestTicketListPriority:
    def test_priority_filter_branch(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            p1 = Ticket(id="aaaa", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
            p2 = Ticket(id="bbbb", status="open", title="Normal", body="", priority=2, created=datetime.now(UTC))
            write_ticket(p1, tickets_dir / "aaaa.md")
            write_ticket(p2, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "-p", "1"])

            assert result.exit_code == 0
            assert "aaaa" in result.output
            assert "bbbb" not in result.output

    def test_priority_filter_backlog(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            backlog_dir = backlog_root(base) / "tickets"
            backlog_dir.mkdir(parents=True, exist_ok=True)

            p1 = Ticket(id="aaaa", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
            p2 = Ticket(id="bbbb", status="open", title="Normal", body="", priority=2, created=datetime.now(UTC))
            write_ticket(p1, backlog_dir / "aaaa.md")
            write_ticket(p2, backlog_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--backlog", "-p", "1"])

            assert result.exit_code == 0
            assert "aaaa" in result.output
            assert "bbbb" not in result.output

    def test_priority_filter_invalid(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "list", "-p", "5"])

            assert result.exit_code == 1
            assert "Invalid priority" in result.output


class TestTicketListTable:
    """Tests for Rich table formatting in tk list."""

    def test_table_has_header_row(self) -> None:
        """The table should include column headers."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="Test ticket", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "ID" in result.output
            assert "Status" in result.output
            assert "Title" in result.output

    def test_table_shows_priority(self) -> None:
        """Priority should be displayed as P1, P2, etc."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="aaaa", status="open", title="High priority", body="", priority=1, created=datetime.now(UTC)
            )
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "P1" in result.output

    def test_table_shows_assignee(self) -> None:
        """Assignee should be visible when set."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="aaaa", status="open", title="Assigned ticket", body="", assignee="alice", created=datetime.now(UTC)
            )
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "@alice" in result.output

    def test_table_shows_deps(self) -> None:
        """Dependencies should be visible in the table."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="aaaa",
                status="open",
                title="Blocked ticket",
                body="",
                deps=["bbbb", "cccc"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "bbbb" in result.output
            assert "cccc" in result.output

    def test_table_all_shows_location_column(self) -> None:
        """With --all flag, the Location column should be present."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="Branch ticket", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list", "--all"])

            assert result.exit_code == 0
            assert "Location" in result.output
            assert "branch:" in result.output

    def test_table_backlog_no_location_column(self) -> None:
        """Without --all flag, no Location column should appear."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="Normal ticket", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "Location" not in result.output

    def test_table_hides_empty_assignee_and_deps_columns(self) -> None:
        """Assignee and Deps columns should be hidden when no ticket has data for them."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="No extras", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "Assignee" not in result.output
            assert "Deps" not in result.output

    def test_json_output_unaffected(self) -> None:
        """JSON output should not contain table formatting."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="JSON ticket", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list", "--json"])

            import json

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["id"] == "aaaa"
            assert data[0]["title"] == "JSON ticket"


class TestFormatTicketSummary:
    def test_all_statuses(self) -> None:
        tickets = [
            Ticket(id="a", status="open", title="", body="", created=datetime.now(UTC)),
            Ticket(id="b", status="open", title="", body="", created=datetime.now(UTC)),
            Ticket(id="c", status="in_progress", title="", body="", created=datetime.now(UTC)),
            Ticket(id="d", status="closed", title="", body="", created=datetime.now(UTC)),
        ]
        result = format_ticket_summary(tickets)
        assert result == "2 open · 1 in_progress · 1 closed · 4 total"

    def test_only_open(self) -> None:
        tickets = [
            Ticket(id="a", status="open", title="", body="", created=datetime.now(UTC)),
        ]
        result = format_ticket_summary(tickets)
        assert result == "1 open · 1 total"

    def test_empty_list(self) -> None:
        result = format_ticket_summary([])
        assert result == "0 total"

    def test_dict_input(self) -> None:
        tickets = [{"status": "open"}, {"status": "closed"}]
        result = format_ticket_summary(tickets)
        assert result == "1 open · 1 closed · 2 total"


class TestTicketShow:
    def test_show_displays_file_path(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-sh01")

            result = runner.invoke(cli.app, ["tk", "show", "kin-sh01"])

            assert result.exit_code == 0, result.output
            assert ".kd/" in result.output
            assert "kin-sh01.md" in result.output

    def test_show_structured_header(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket = Ticket(
                id="ab12",
                status="open",
                title="Fix the bug",
                body="Details here",
                priority=1,
                type="bug",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "ab12.md")

            result = runner.invoke(cli.app, ["tk", "show", "ab12"])

            assert result.exit_code == 0
            # Structured header — no raw frontmatter
            assert "ab12" in result.output
            assert "open" in result.output
            assert "P1" in result.output
            assert "bug" in result.output
            assert "Fix the bug" in result.output
            # Should NOT contain raw YAML delimiters
            assert "---" not in result.output

    def test_show_no_raw_frontmatter(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket = Ticket(
                id="cd34",
                status="in_progress",
                title="Add feature",
                body="## AC\n\n- [ ] Done",
                deps=["ab12"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "cd34.md")

            result = runner.invoke(cli.app, ["tk", "show", "cd34"])

            assert result.exit_code == 0
            assert "deps" in result.output  # structured deps display
            assert "ab12" in result.output

    def test_show_dep_status_inline(self) -> None:
        """Dep statuses should appear inline, e.g. 'deps  ab12 closed'."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            # Create the dep ticket (closed)
            dep_ticket = Ticket(
                id="ab12",
                status="closed",
                title="Dep ticket",
                body="",
                created=datetime.now(UTC),
            )
            write_ticket(dep_ticket, tickets_dir / "ab12.md")

            # Create a ticket that depends on ab12
            ticket = Ticket(
                id="cd34",
                status="open",
                title="Has dep",
                body="",
                deps=["ab12"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "cd34.md")

            result = runner.invoke(cli.app, ["tk", "show", "cd34"])

            assert result.exit_code == 0
            assert "deps" in result.output
            assert "ab12" in result.output
            assert "closed" in result.output

    def test_show_dep_status_unknown_when_not_found(self) -> None:
        """When a dep ticket doesn't exist, status should show as 'unknown'."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="ef56",
                status="open",
                title="Has missing dep",
                body="",
                deps=["zzzz"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "ef56.md")

            result = runner.invoke(cli.app, ["tk", "show", "ef56"])

            assert result.exit_code == 0
            assert "deps" in result.output
            assert "zzzz" in result.output
            assert "unknown" in result.output

    def test_show_dep_status_multiple_deps(self) -> None:
        """Multiple deps should each show their status."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            dep1 = Ticket(id="aa11", status="closed", title="Dep 1", body="", created=datetime.now(UTC))
            dep2 = Ticket(id="bb22", status="open", title="Dep 2", body="", created=datetime.now(UTC))
            write_ticket(dep1, tickets_dir / "aa11.md")
            write_ticket(dep2, tickets_dir / "bb22.md")

            ticket = Ticket(
                id="cc33",
                status="in_progress",
                title="Has two deps",
                body="",
                deps=["aa11", "bb22"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "cc33.md")

            result = runner.invoke(cli.app, ["tk", "show", "cc33"])

            assert result.exit_code == 0
            assert "aa11" in result.output
            assert "closed" in result.output
            assert "bb22" in result.output
            assert "open" in result.output

    def test_show_json_dep_status(self) -> None:
        """JSON output should include dep status as objects with id and status."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            dep_ticket = Ticket(
                id="ab12",
                status="closed",
                title="Dep ticket",
                body="",
                created=datetime.now(UTC),
            )
            write_ticket(dep_ticket, tickets_dir / "ab12.md")

            ticket = Ticket(
                id="cd34",
                status="open",
                title="Has dep",
                body="",
                deps=["ab12"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "cd34.md")

            result = runner.invoke(cli.app, ["tk", "show", "cd34", "--json"])

            assert result.exit_code == 0
            import json

            data = json.loads(result.output)
            assert len(data["deps"]) == 1
            assert data["deps"][0]["id"] == "ab12"
            assert data["deps"][0]["status"] == "closed"

    def test_show_panel_layout_contains_metadata_grid(self) -> None:
        """Panel should contain a grid with status, priority, type, and created rows."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket = Ticket(
                id="ff99",
                status="open",
                title="Panel test",
                body="Some body text",
                priority=1,
                type="bug",
                created=datetime(2026, 1, 15, tzinfo=UTC),
            )
            write_ticket(ticket, tickets_dir / "ff99.md")

            result = runner.invoke(cli.app, ["tk", "show", "ff99"])

            assert result.exit_code == 0
            output = result.output
            # Panel border character
            assert "─" in output or "╭" in output or "│" in output
            # Metadata fields present as grid rows
            assert "status" in output
            assert "open" in output
            assert "priority" in output
            assert "P1" in output
            assert "type" in output
            assert "bug" in output
            assert "created" in output
            assert "2026-01-15" in output
            # Title in panel header
            assert "ff99" in output
            assert "Panel test" in output
            # Body content
            assert "Some body text" in output

    def test_show_panel_shows_assignee_when_present(self) -> None:
        """Assignee row should appear in panel when ticket has an assignee."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket = Ticket(
                id="ee88",
                status="in_progress",
                title="Assigned ticket",
                body="",
                assignee="hand",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "ee88.md")

            result = runner.invoke(cli.app, ["tk", "show", "ee88"])

            assert result.exit_code == 0
            assert "assignee" in result.output
            assert "hand" in result.output

    def test_show_panel_hides_assignee_when_absent(self) -> None:
        """Assignee row should not appear when ticket has no assignee."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket = Ticket(
                id="dd77",
                status="open",
                title="Unassigned ticket",
                body="",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "dd77.md")

            result = runner.invoke(cli.app, ["tk", "show", "dd77"])

            assert result.exit_code == 0
            assert "assignee" not in result.output

    def test_show_panel_shows_links(self) -> None:
        """Links row should appear when ticket has links."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket = Ticket(
                id="cc66",
                status="open",
                title="Linked ticket",
                body="",
                links=["https://example.com/issue/1"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "cc66.md")

            result = runner.invoke(cli.app, ["tk", "show", "cc66"])

            assert result.exit_code == 0
            assert "links" in result.output
            assert "https://example.com/issue/1" in result.output

    def test_show_panel_subtitle_has_file_path(self) -> None:
        """Panel subtitle should show the relative file path."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "bb55")

            result = runner.invoke(cli.app, ["tk", "show", "bb55"])

            assert result.exit_code == 0
            assert "bb55.md" in result.output
            assert ".kd/" in result.output


class TestMigrate:
    def test_dry_run_shows_changes(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-ab12")

            result = runner.invoke(cli.app, ["migrate"])

            assert result.exit_code == 0, result.output
            assert "rename:" in result.output
            assert "rewrite:" in result.output
            assert "Dry run complete" in result.output

            # File should NOT have been renamed (dry-run)
            assert (tickets_dir / "kin-ab12.md").exists()
            assert not (tickets_dir / "ab12.md").exists()

    def test_apply_renames_and_rewrites(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            # Create ticket with a dep that references another kin- ID
            ticket = Ticket(
                id="kin-ab12",
                status="open",
                title="Test",
                body="See kin-cd34 for details",
                deps=["kin-cd34"],
                created=datetime.now(UTC),
            )
            path = tickets_dir / "kin-ab12.md"
            tickets_dir.mkdir(parents=True, exist_ok=True)
            write_ticket(ticket, path)

            result = runner.invoke(cli.app, ["migrate", "--apply"])

            assert result.exit_code == 0, result.output
            assert "Migrated" in result.output

            # File should be renamed
            assert not (tickets_dir / "kin-ab12.md").exists()
            assert (tickets_dir / "ab12.md").exists()

            # Content should have kin- prefix removed
            content = (tickets_dir / "ab12.md").read_text()
            assert "kin-ab12" not in content
            assert 'id: "ab12"' in content
            assert "kin-cd34" not in content
            assert "cd34" in content

    def test_apply_is_idempotent(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-ab12")

            runner.invoke(cli.app, ["migrate", "--apply"])
            result = runner.invoke(cli.app, ["migrate", "--apply"])

            assert result.exit_code == 0
            assert "0 files renamed" in result.output

    def test_collision_aborts(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-ab12")
            # Create a file that would collide
            (tickets_dir / "ab12.md").write_text("collision")

            result = runner.invoke(cli.app, ["migrate", "--apply"])

            assert result.exit_code == 1
            assert "collision" in result.output


class TestTicketCloseUnblocked:
    def test_close_shows_newly_unblocked_ticket(self) -> None:
        """Closing a dep should print the ticket that becomes unblocked."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

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

            result = runner.invoke(cli.app, ["tk", "close", "blk1"])

            assert result.exit_code == 0, result.output
            assert "Unblocked 1 ticket(s):" in result.output
            assert "dep1" in result.output
            assert "Waiting on blocker" in result.output

    def test_close_no_unblocked_when_other_deps_remain(self) -> None:
        """If the blocked ticket has other open deps, it should NOT be listed."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

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
            result = runner.invoke(cli.app, ["tk", "close", "bk01"])

            assert result.exit_code == 0, result.output
            assert "Unblocked" not in result.output

    def test_close_unblocked_when_all_deps_closed(self) -> None:
        """Closing the last open dep should show the ticket as unblocked."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

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
            result = runner.invoke(cli.app, ["tk", "close", "bk12"])

            assert result.exit_code == 0, result.output
            assert "Unblocked 1 ticket(s):" in result.output
            assert "dep3" in result.output
            assert "Almost free" in result.output

    def test_close_no_message_when_no_deps(self) -> None:
        """Closing a ticket nobody depends on should not print unblocked message."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            standalone = Ticket(id="solo", status="open", title="Standalone", body="", created=datetime.now(UTC))
            write_ticket(standalone, tickets_dir / "solo.md")

            result = runner.invoke(cli.app, ["tk", "close", "solo"])

            assert result.exit_code == 0, result.output
            assert "Unblocked" not in result.output

    def test_close_multiple_unblocked(self) -> None:
        """Closing one blocker can unblock multiple tickets."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

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

            result = runner.invoke(cli.app, ["tk", "close", "bk21"])

            assert result.exit_code == 0, result.output
            assert "Unblocked 2 ticket(s):" in result.output
            assert "da01" in result.output
            assert "db01" in result.output

    def test_close_does_not_show_already_closed_dependents(self) -> None:
        """Already-closed tickets that depend on the blocker should not appear as unblocked."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

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

            result = runner.invoke(cli.app, ["tk", "close", "bk31"])

            assert result.exit_code == 0, result.output
            assert "Unblocked" not in result.output


class TestTicketLog:
    def test_log_appends_worklog_entry(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-lg01")

            result = runner.invoke(cli.app, ["tk", "log", "kin-lg01", "Started working on this"])

            assert result.exit_code == 0, result.output
            assert "kin-lg01" in result.output
            assert "Started working on this" in result.output

            # Verify the file was updated
            content = (tickets_dir / "kin-lg01.md").read_text()
            assert "## Worklog" in content
            assert "Started working on this" in content

    def test_log_multiple_entries(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-lg02")

            runner.invoke(cli.app, ["tk", "log", "kin-lg02", "First entry"])
            result = runner.invoke(cli.app, ["tk", "log", "kin-lg02", "Second entry"])

            assert result.exit_code == 0, result.output

            content = (tickets_dir / "kin-lg02.md").read_text()
            assert "First entry" in content
            assert "Second entry" in content

            # Order matters: first before second
            first_pos = content.index("First entry")
            second_pos = content.index("Second entry")
            assert first_pos < second_pos

    def test_log_not_found(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "log", "kin-nope", "message"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_log_preserves_ticket_content(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="kin-lg03",
                status="open",
                title="Preserve content",
                body="## Acceptance Criteria\n\n- [ ] Item 1\n- [ ] Item 2",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "kin-lg03.md")

            result = runner.invoke(cli.app, ["tk", "log", "kin-lg03", "Did some work"])

            assert result.exit_code == 0, result.output

            content = (tickets_dir / "kin-lg03.md").read_text()
            assert "# Preserve content" in content
            assert "## Acceptance Criteria" in content
            assert "- [ ] Item 1" in content
            assert "- [ ] Item 2" in content
            assert "Did some work" in content

    def test_log_missing_message_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-lg04")

            result = runner.invoke(cli.app, ["tk", "log", "kin-lg04"])

            assert result.exit_code != 0


class TestTicketDep:
    """Tests for kd tk dep — adding dependencies."""

    def test_dep_appends_not_overwrites(self) -> None:
        """Adding a second dep must preserve the first (append, not overwrite).

        Uses the exact IDs from the bug report: cf1a depends on 3642 then d869.
        """
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            # Create three tickets — 3642 is all-numeric (the tricky case)
            for tid in ["cf1a", "3642", "d869"]:
                t = Ticket(
                    id=tid,
                    status="open",
                    title=f"Ticket {tid}",
                    body="",
                    created=datetime.now(UTC),
                )
                write_ticket(t, tickets_dir / f"{tid}.md")

            # First dep: cf1a depends on 3642
            result1 = runner.invoke(cli.app, ["tk", "dep", "cf1a", "3642"])
            assert result1.exit_code == 0, result1.output
            assert "now depends on" in result1.output

            # Second dep: cf1a depends on d869
            result2 = runner.invoke(cli.app, ["tk", "dep", "cf1a", "d869"])
            assert result2.exit_code == 0, result2.output
            assert "now depends on" in result2.output

            # Both deps must be present
            found = find_ticket(base, "cf1a")
            assert found is not None
            ticket, _ = found
            assert "3642" in ticket.deps, f"First dep lost! deps={ticket.deps}"
            assert "d869" in ticket.deps, f"Second dep missing! deps={ticket.deps}"
            assert len(ticket.deps) == 2

    def test_dep_preserves_existing_deps_on_disk(self) -> None:
        """A ticket with pre-existing deps on disk must keep them when adding a new dep."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            # Create dep tickets
            for tid in ["3642", "d869"]:
                t = Ticket(id=tid, status="open", title=f"Ticket {tid}", body="", created=datetime.now(UTC))
                write_ticket(t, tickets_dir / f"{tid}.md")

            # Create target ticket already having one dep on disk
            target = Ticket(
                id="cf1a",
                status="open",
                title="Target ticket",
                body="",
                deps=["3642"],
                created=datetime.now(UTC),
            )
            write_ticket(target, tickets_dir / "cf1a.md")

            # Verify first dep survives write/read roundtrip
            found_before = find_ticket(base, "cf1a")
            assert found_before is not None
            ticket_before, _ = found_before
            assert "3642" in ticket_before.deps, f"Dep lost after roundtrip! deps={ticket_before.deps}"

            # Add second dep via CLI
            result = runner.invoke(cli.app, ["tk", "dep", "cf1a", "d869"])
            assert result.exit_code == 0, result.output
            assert "now depends on" in result.output

            # Both deps must be present
            found = find_ticket(base, "cf1a")
            assert found is not None
            ticket, _ = found
            assert "3642" in ticket.deps, f"First dep lost! deps={ticket.deps}"
            assert "d869" in ticket.deps, f"Second dep missing! deps={ticket.deps}"
            assert len(ticket.deps) == 2

    def test_dep_survives_status_change(self) -> None:
        """Deps must survive when ticket status changes between dep adds."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            for tid in ["cf1a", "aaaa", "bbbb"]:
                t = Ticket(id=tid, status="open", title=f"Ticket {tid}", body="", created=datetime.now(UTC))
                write_ticket(t, tickets_dir / f"{tid}.md")

            # Add first dep
            runner.invoke(cli.app, ["tk", "dep", "cf1a", "aaaa"])
            # Change status (rewrites ticket)
            runner.invoke(cli.app, ["tk", "start", "cf1a"])
            # Add second dep
            runner.invoke(cli.app, ["tk", "dep", "cf1a", "bbbb"])

            found = find_ticket(base, "cf1a")
            assert found is not None
            ticket, _ = found
            assert ticket.status == "in_progress"
            assert "aaaa" in ticket.deps, f"First dep lost after status change! deps={ticket.deps}"
            assert "bbbb" in ticket.deps, f"Second dep missing! deps={ticket.deps}"
            assert len(ticket.deps) == 2

    def test_dep_idempotent(self) -> None:
        """Adding the same dep twice should be a no-op the second time."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            for tid in ["cf1a", "aaaa"]:
                t = Ticket(
                    id=tid,
                    status="open",
                    title=f"Ticket {tid}",
                    body="",
                    created=datetime.now(UTC),
                )
                write_ticket(t, tickets_dir / f"{tid}.md")

            # Add dep twice
            runner.invoke(cli.app, ["tk", "dep", "cf1a", "aaaa"])
            result = runner.invoke(cli.app, ["tk", "dep", "cf1a", "aaaa"])

            assert result.exit_code == 0
            assert "already depends on" in result.output

            found = find_ticket(base, "cf1a")
            assert found is not None
            ticket, _ = found
            assert ticket.deps == ["aaaa"]

    def test_dep_not_found(self) -> None:
        """Adding a dep with a nonexistent ticket should error."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            t = Ticket(id="cf1a", status="open", title="Target", body="", created=datetime.now(UTC))
            write_ticket(t, tickets_dir / "cf1a.md")

            result = runner.invoke(cli.app, ["tk", "dep", "cf1a", "zzzz"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestNoResultsMessages:
    """Tests for helpful empty-state messages with next-step guidance."""

    def test_list_empty_branch_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "list"])

            assert result.exit_code == 0
            assert "No tickets found" in result.output
            assert "kd tk create" in result.output

    def test_list_empty_backlog_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "list", "--backlog"])

            assert result.exit_code == 0
            assert "No backlog tickets" in result.output
            assert "kd tk create --backlog" in result.output

    def test_list_all_empty_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "list", "--all"])

            assert result.exit_code == 0
            assert "No tickets found" in result.output
            assert "kd tk create" in result.output

    def test_ready_empty_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "ready"])

            assert result.exit_code == 0
            assert "No ready tickets" in result.output
            assert "kd tk create" in result.output

    def test_ready_excludes_in_review(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
            review_ticket = Ticket(
                id="bbbb", status="in_review", title="Review ticket", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "aaaa.md")
            write_ticket(review_ticket, tickets_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "ready"])

            assert result.exit_code == 0
            assert "Branch:" in result.output
            assert "aaaa" in result.output
            assert "bbbb" not in result.output

    def test_ready_separates_branch_and_backlog(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            backlog_dir = backlog_root(base) / "tickets"
            backlog_dir.mkdir(parents=True, exist_ok=True)

            branch_tk = Ticket(id="aaaa", status="open", title="Branch task", body="", created=datetime.now(UTC))
            backlog_tk = Ticket(id="bbbb", status="open", title="Backlog task", body="", created=datetime.now(UTC))
            write_ticket(branch_tk, tickets_dir / "aaaa.md")
            write_ticket(backlog_tk, backlog_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "ready"])

            assert result.exit_code == 0
            lines = result.output.strip().split("\n")
            assert lines[0] == "Branch:"
            assert "aaaa" in lines[1]
            # blank line separator
            assert lines[2] == ""
            assert lines[3] == "Backlog:"
            assert "bbbb" in lines[4]

    def test_ready_backlog_only(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            backlog_dir = backlog_root(base) / "tickets"
            backlog_dir.mkdir(parents=True, exist_ok=True)

            backlog_tk = Ticket(id="cccc", status="open", title="Backlog only", body="", created=datetime.now(UTC))
            write_ticket(backlog_tk, backlog_dir / "cccc.md")

            result = runner.invoke(cli.app, ["tk", "ready"])

            assert result.exit_code == 0
            assert "Branch:" not in result.output
            assert "Backlog:" in result.output
            assert "cccc" in result.output

    def test_show_all_empty_branch_shows_guidance(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "show", "--all"])

            assert result.exit_code == 0
            assert "No tickets on this branch" in result.output
            assert "kd tk create" in result.output


class TestFormatTicketLine:
    """Tests for the format_ticket_line helper."""

    def test_basic_line_no_deps(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Fix bug", body="", created=datetime.now(UTC))
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][open] - Fix bug"

    def test_line_with_deps(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(
            id="ab12", status="open", title="Fix bug", body="", deps=["cd34", "ef56"], created=datetime.now(UTC)
        )
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][open] - Fix bug  <- cd34, ef56"

    def test_line_with_single_dep(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(
            id="ab12", status="in_progress", title="Work", body="", deps=["zz99"], created=datetime.now(UTC)
        )
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][in_progress] - Work  <- zz99"

    def test_line_with_location(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Task", body="", created=datetime.now(UTC))
        line = format_ticket_line(ticket, location="backlog")
        assert line == "ab12 [P2][open] - Task (backlog)"

    def test_line_with_deps_and_location(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Task", body="", deps=["cd34"], created=datetime.now(UTC))
        line = format_ticket_line(ticket, location="branch:main")
        assert line == "ab12 [P2][open] - Task (branch:main)  <- cd34"

    def test_line_with_assignee(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Task", body="", assignee="alice", created=datetime.now(UTC))
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][open] @alice - Task"

    def test_line_priority_1(self) -> None:
        from kingdom.cli import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
        line = format_ticket_line(ticket)
        assert line == "ab12 [P1][open] - Urgent"


class TestTicketListDepsJson:
    """Tests for deps in JSON output of tk list."""

    def test_json_includes_deps_field(self) -> None:
        """JSON output should include deps array for each ticket."""
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="aaaa",
                status="open",
                title="Blocked",
                body="",
                deps=["bbbb", "cccc"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["deps"] == ["bbbb", "cccc"]

    def test_json_empty_deps_array(self) -> None:
        """Tickets with no deps should have empty deps array in JSON."""
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(id="aaaa", status="open", title="No deps", body="", created=datetime.now(UTC))
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data[0]["deps"] == []

    def test_json_all_includes_deps(self) -> None:
        """--all --json should include deps field."""
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="aaaa",
                status="open",
                title="With deps",
                body="",
                deps=["xxxx"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "aaaa.md")

            result = runner.invoke(cli.app, ["tk", "list", "--all", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            matching = [t for t in data if t["id"] == "aaaa"]
            assert len(matching) == 1
            assert matching[0]["deps"] == ["xxxx"]

    def test_json_backlog_includes_deps(self) -> None:
        """--backlog --json should include deps field."""
        import json

        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            backlog_dir = backlog_root(base) / "tickets"

            ticket = Ticket(
                id="bbbb",
                status="open",
                title="Backlog with deps",
                body="",
                deps=["aaaa"],
                created=datetime.now(UTC),
            )
            write_ticket(ticket, backlog_dir / "bbbb.md")

            result = runner.invoke(cli.app, ["tk", "list", "--backlog", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["deps"] == ["aaaa"]
