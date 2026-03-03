"""Tests for kd tk show command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
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


class TestTicketShow:
    def test_show_displays_file_path(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "kin-sh01")

        result = runner.invoke(ticket_app, ["show", "kin-sh01"])

        assert result.exit_code == 0, result.output
        assert ".kd/" in result.output
        assert "kin-sh01.md" in result.output

    def test_show_structured_header(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
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

        result = runner.invoke(ticket_app, ["show", "ab12"])

        assert result.exit_code == 0
        # Structured header — no raw frontmatter
        assert "ab12" in result.output
        assert "open" in result.output
        assert "P1" in result.output
        assert "bug" in result.output
        assert "Fix the bug" in result.output
        # Should NOT contain raw YAML delimiters
        assert "---" not in result.output

    def test_show_no_raw_frontmatter(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="cd34",
            status="in_progress",
            title="Add feature",
            body="## AC\n\n- [ ] Done",
            deps=["ab12"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "cd34.md")

        result = runner.invoke(ticket_app, ["show", "cd34"])

        assert result.exit_code == 0
        assert "deps" in result.output  # structured deps display
        assert "ab12" in result.output

    def test_show_dep_status_inline(self, cli_project: Path) -> None:
        """Dep statuses should appear inline, e.g. 'deps  ab12 closed'."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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

        result = runner.invoke(ticket_app, ["show", "cd34"])

        assert result.exit_code == 0
        assert "deps" in result.output
        assert "ab12" in result.output
        assert "closed" in result.output

    def test_show_dep_status_unknown_when_not_found(self, cli_project: Path) -> None:
        """When a dep ticket doesn't exist, status should show as 'unknown'."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(
            id="ef56",
            status="open",
            title="Has missing dep",
            body="",
            deps=["zzzz"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "ef56.md")

        result = runner.invoke(ticket_app, ["show", "ef56"])

        assert result.exit_code == 0
        assert "deps" in result.output
        assert "zzzz" in result.output
        assert "unknown" in result.output

    def test_show_dep_status_multiple_deps(self, cli_project: Path) -> None:
        """Multiple deps should each show their status."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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

        result = runner.invoke(ticket_app, ["show", "cc33"])

        assert result.exit_code == 0
        assert "aa11" in result.output
        assert "closed" in result.output
        assert "bb22" in result.output
        assert "open" in result.output

    def test_show_json_dep_status(self, cli_project: Path) -> None:
        """JSON output should include dep status as objects with id and status."""
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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

        result = runner.invoke(ticket_app, ["show", "cd34", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["deps"]) == 1
        assert data["deps"][0]["id"] == "ab12"
        assert data["deps"][0]["status"] == "closed"

    def test_show_panel_layout_contains_metadata_grid(self, cli_project: Path) -> None:
        """Panel should contain a grid with status, priority, type, and created rows."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
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

        result = runner.invoke(ticket_app, ["show", "ff99"])

        assert result.exit_code == 0
        output = result.output
        # Panel border character
        assert "\u2500" in output or "\u256d" in output or "\u2502" in output
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

    def test_show_panel_shows_assignee_when_present(self, cli_project: Path) -> None:
        """Assignee row should appear in panel when ticket has an assignee."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="ee88",
            status="in_progress",
            title="Assigned ticket",
            body="",
            assignee="hand",
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "ee88.md")

        result = runner.invoke(ticket_app, ["show", "ee88"])

        assert result.exit_code == 0
        assert "assignee" in result.output
        assert "hand" in result.output

    def test_show_panel_hides_assignee_when_absent(self, cli_project: Path) -> None:
        """Assignee row should not appear when ticket has no assignee."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="dd77",
            status="open",
            title="Unassigned ticket",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "dd77.md")

        result = runner.invoke(ticket_app, ["show", "dd77"])

        assert result.exit_code == 0
        assert "assignee" not in result.output

    def test_show_panel_shows_links(self, cli_project: Path) -> None:
        """Links row should appear when ticket has links."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="cc66",
            status="open",
            title="Linked ticket",
            body="",
            links=["https://example.com/issue/1"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "cc66.md")

        result = runner.invoke(ticket_app, ["show", "cc66"])

        assert result.exit_code == 0
        assert "links" in result.output
        assert "https://example.com/issue/1" in result.output

    def test_show_panel_subtitle_has_file_path(self, cli_project: Path) -> None:
        """Panel subtitle should show the relative file path."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        create_ticket_in(tickets_dir, "bb55")

        result = runner.invoke(ticket_app, ["show", "bb55"])

        assert result.exit_code == 0
        assert "bb55.md" in result.output
        assert ".kd/" in result.output


class TestTicketShowRelationships:
    """Tests for show enriched view with Blockers/Blocking/Children/Linked."""

    def test_show_displays_blocking(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Blocker", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Blocked", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["show", "aaaa"])
        assert result.exit_code == 0
        assert "Blocking" in result.output
        assert "bbbb" in result.output

    def test_show_displays_children(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Parent", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(
                id="bbbb",
                status="open",
                title="Child",
                body="",
                parent="aaaa",
                created=datetime.now(UTC),
            ),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["show", "aaaa"])
        assert result.exit_code == 0
        assert "Children" in result.output
        assert "bbbb" in result.output
