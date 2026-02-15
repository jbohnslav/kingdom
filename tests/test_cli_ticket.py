"""Tests for the ticket CLI commands (create, close, reopen, pull)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    ensure_branch_layout,
    ensure_run_layout,
    set_current_run,
)
from kingdom.ticket import Ticket, find_ticket, write_ticket

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
            assert "Backlog ticket" in output

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
            assert "Pulled kin-pull:" in result.output
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
            assert "Pulled kin-legacy:" in result.output

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
            branch_tickets = branch_root(base, BRANCH) / "tickets" / "kin-mv01.md"
            assert branch_tickets.exists()
            # Source must be removed (no duplicate in backlog)
            assert not (backlog_dir / "kin-mv01.md").exists()

    def test_move_already_in_destination(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            create_ticket_in(tickets_dir, "kin-mv02")

            result = runner.invoke(cli.app, ["tk", "move", "kin-mv02"])

            assert result.exit_code == 0, result.output
            assert "already in" in result.output

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
            assert "Open ticket" in result.output
            assert "Closed ticket" not in result.output


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
            assert "deps:" in result.output  # structured deps display
            assert "ab12" in result.output


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
            assert "Migrated:" in result.output

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
