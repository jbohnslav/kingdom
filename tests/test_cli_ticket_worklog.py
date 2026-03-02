"""Tests for kd tk log (worklog) commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import branch_root
from kingdom.ticket import Ticket, write_ticket

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


class TestTicketLog:
    def test_log_appends_worklog_entry(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg01")

        result = runner.invoke(cli.app, ["tk", "log", "kin-lg01", "Started working on this"])

        assert result.exit_code == 0, result.output
        assert "kin-lg01" in result.output
        assert "Started working on this" in result.output

        # Verify the file was updated
        content = (tickets_dir / "kin-lg01.md").read_text()
        assert "## Worklog" in content
        assert "Started working on this" in content

    def test_log_multiple_entries(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
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

    def test_log_not_found(self, cli_project: Path) -> None:
        result = runner.invoke(cli.app, ["tk", "log", "kin-nope", "message"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_log_preserves_ticket_content(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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

    def test_log_missing_message_errors(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-lg04")

        result = runner.invoke(cli.app, ["tk", "log", "kin-lg04"])

        assert result.exit_code != 0
