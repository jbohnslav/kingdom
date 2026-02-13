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
    set_current_run,
)
from kingdom.ticket import Ticket, write_ticket

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
    def test_create_prints_absolute_path(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "My new ticket"])

            assert result.exit_code == 0, result.output
            output = result.output.strip()
            assert output.startswith("/")
            assert output.endswith(".md")
            assert Path(output).exists()

    def test_create_backlog_prints_path(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Backlog ticket", "--backlog"])

            assert result.exit_code == 0, result.output
            output = result.output.strip()
            assert "backlog" in output
            assert Path(output).exists()

    def test_create_out_of_range_priority_clamps(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "create", "Bad priority", "-p", "5"])

            assert result.exit_code == 0
            # First line of output should be the path
            first_line = result.output.strip().split("\n")[0]
            assert first_line.endswith(".md")
            assert Path(first_line).exists()


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
            output = result.output.strip()
            assert output.endswith("kin-pull.md")
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
            assert "not in the backlog" in result.output

    def test_pull_not_found_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "pull", "kin-nope"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_pull_no_active_run_errors(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            # Don't call setup_project — no active run

            backlog_dir = backlog_root(base) / "tickets"
            create_ticket_in(backlog_dir, "kin-norun")

            result = runner.invoke(cli.app, ["tk", "pull", "kin-norun"])

            assert result.exit_code == 1

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
