"""Tests for ticket list, show --all, formatting, and filter commands."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli.ticket import format_ticket_summary, ticket_app
from kingdom.state import (
    backlog_root,
    branch_root,
    ensure_branch_layout,
    resolve_execution_context,
)
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


class TestTicketList:
    def test_list_hides_closed_by_default(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        # Create one open and one closed ticket
        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "Open ticket" in result.output
        assert "Closed ticket" not in result.output

    def test_list_include_closed_shows_all(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--closed"])

        assert result.exit_code == 0
        assert "Open ticket" in result.output
        assert "Closed ticket" in result.output

    def test_list_all_hides_closed_by_default(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--all"])

        assert result.exit_code == 0
        # Rich table may wrap long titles; check ticket IDs instead
        assert "aaaa" in result.output
        assert "bbbb" not in result.output

    def test_list_status_filter_open(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        in_progress = Ticket(
            id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
        )
        closed_ticket = Ticket(id="cccc", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(in_progress, tickets_dir / "bbbb.md")
        write_ticket(closed_ticket, tickets_dir / "cccc.md")

        result = runner.invoke(ticket_app, ["list", "--status", "open"])

        assert result.exit_code == 0
        assert "Open ticket" in result.output
        assert "In-progress ticket" not in result.output
        assert "Closed ticket" not in result.output

    def test_list_status_filter_in_progress(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        in_progress = Ticket(
            id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
        )
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(in_progress, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--status", "in_progress"])

        assert result.exit_code == 0
        assert "Open ticket" not in result.output
        assert "In-progress ticket" in result.output

    def test_list_status_filter_closed(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        # --status closed should show closed tickets even without --include-closed
        result = runner.invoke(ticket_app, ["list", "--status", "closed"])

        assert result.exit_code == 0
        assert "Open ticket" not in result.output
        assert "Closed ticket" in result.output

    def test_list_status_filter_in_review(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        review_ticket = Ticket(id="bbbb", status="in_review", title="Review ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(review_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--status", "in_review"])

        assert result.exit_code == 0
        assert "Open ticket" not in result.output
        assert "Review ticket" in result.output

    def test_list_shows_in_review_by_default(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        review_ticket = Ticket(id="aaaa", status="in_review", title="Review ticket", body="", created=datetime.now(UTC))
        write_ticket(review_ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "Review ticket" in result.output

    def test_list_status_filter_summary_reflects_filter(self, cli_project: Path) -> None:
        """Summary line should count only filtered tickets."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        t1 = Ticket(id="aaaa", status="open", title="Open one", body="", created=datetime.now(UTC))
        t2 = Ticket(id="bbbb", status="closed", title="Closed one", body="", created=datetime.now(UTC))
        t3 = Ticket(id="cccc", status="closed", title="Closed two", body="", created=datetime.now(UTC))
        write_ticket(t1, tickets_dir / "aaaa.md")
        write_ticket(t2, tickets_dir / "bbbb.md")
        write_ticket(t3, tickets_dir / "cccc.md")

        result = runner.invoke(ticket_app, ["list", "--status", "closed"])

        assert result.exit_code == 0
        assert "2 closed" in result.output
        assert "2 total" in result.output
        assert "3 total" not in result.output

    def test_list_status_filter_invalid(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list", "--status", "bogus"])

        assert result.exit_code == 1
        assert "Invalid status" in result.output

    def test_list_status_filter_with_all(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--all", "--status", "closed"])

        assert result.exit_code == 0
        # Rich table may wrap long titles; check ticket IDs instead
        assert "aaaa" not in result.output
        assert "bbbb" in result.output

    def test_list_status_filter_short_flag(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        in_progress = Ticket(
            id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
        )
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(in_progress, tickets_dir / "bbbb.md")

        # Use -s short flag
        result = runner.invoke(ticket_app, ["list", "-s", "open"])

        assert result.exit_code == 0
        assert "Open ticket" in result.output
        assert "In-progress ticket" not in result.output

    def test_list_summary_line_shows_counts(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        ip_ticket = Ticket(
            id="bbbb", status="in_progress", title="In-progress ticket", body="", created=datetime.now(UTC)
        )
        closed_ticket = Ticket(id="cccc", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(ip_ticket, tickets_dir / "bbbb.md")
        write_ticket(closed_ticket, tickets_dir / "cccc.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        # Summary should only count displayed tickets (closed are hidden by default)
        assert "1 open" in result.output
        assert "1 in_progress" in result.output
        assert "1 closed" not in result.output
        assert "2 total" in result.output

    def test_list_summary_line_not_in_json_output(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="A ticket", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--json"])

        assert result.exit_code == 0
        assert "total" not in result.output

    def test_list_summary_with_all_flag(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Closed ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--all"])

        assert result.exit_code == 0
        assert "1 open" in result.output
        # Closed tickets are hidden by default, so summary should not include them
        assert "1 closed" not in result.output
        assert "1 total" in result.output

    def test_list_no_tickets_shows_no_summary(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "total" not in result.output


class TestTicketListClosedCount:
    """Tests for showing closed ticket count when no open tickets remain."""

    def test_only_closed_tickets_shows_count(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        closed1 = Ticket(id="aaaa", status="closed", title="Done 1", body="", created=datetime.now(UTC))
        closed2 = Ticket(id="bbbb", status="closed", title="Done 2", body="", created=datetime.now(UTC))
        write_ticket(closed1, tickets_dir / "aaaa.md")
        write_ticket(closed2, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "No open tickets (2 closed)" in result.output
        assert "--closed" in result.output

    def test_open_tickets_exist_no_closed_hint(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open", body="", created=datetime.now(UTC))
        closed_ticket = Ticket(id="bbbb", status="closed", title="Done", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(closed_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "Open" in result.output
        assert "No open tickets" not in result.output

    def test_no_tickets_at_all_shows_create_hint(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "No tickets found" in result.output
        assert "closed" not in result.output

    def test_only_closed_with_all_flag(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        closed = Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC))
        write_ticket(closed, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--all"])

        assert result.exit_code == 0
        assert "No open tickets (1 closed)" in result.output
        assert "--closed" in result.output

    def test_only_closed_in_backlog(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        backlog_dir.mkdir(parents=True, exist_ok=True)

        closed = Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC))
        write_ticket(closed, backlog_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--backlog"])

        assert result.exit_code == 0
        assert "No open backlog tickets (1 closed)" in result.output
        assert "--closed" in result.output

    def test_closed_flag_shows_closed_tickets_directly(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        closed = Ticket(id="aaaa", status="closed", title="Done ticket", body="", created=datetime.now(UTC))
        write_ticket(closed, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--closed"])

        assert result.exit_code == 0
        assert "Done ticket" in result.output
        assert "No open tickets" not in result.output

    def test_status_filter_no_closed_hint(self, cli_project: Path) -> None:
        """--status in_progress with only closed tickets should not say 'No open tickets'."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        closed = Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC))
        write_ticket(closed, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--status", "in_progress"])

        assert result.exit_code == 0
        assert "No open tickets" not in result.output
        assert "No tickets found" in result.output

    def test_blocked_filter_no_closed_hint(self, cli_project: Path) -> None:
        """--blocked with only closed tickets should not show the closed hint."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        closed = Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC))
        write_ticket(closed, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--blocked"])

        assert result.exit_code == 0
        assert "No open tickets" not in result.output
        assert "No tickets found" in result.output

    def test_ready_filter_no_closed_hint(self, cli_project: Path) -> None:
        """--ready with only closed tickets should not show the closed hint."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        closed = Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC))
        write_ticket(closed, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--ready"])

        assert result.exit_code == 0
        assert "No open tickets" not in result.output
        assert "No tickets found" in result.output


class TestTicketListRecentlyClosed:
    def test_recently_closed_empty_branch_message_mentions_recently_closed(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="open", status="open", title="Open work", body="", created=datetime.now(UTC)),
            tickets_dir / "open.md",
        )

        result = runner.invoke(ticket_app, ["list", "--recently-closed"])

        assert result.exit_code == 0, result.output
        assert "No recently closed tickets found on this branch." in result.output
        assert "No tickets found. Create one" not in result.output

    def test_recently_closed_orders_by_closed_at(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        oldest = Ticket(
            id="old1",
            status="closed",
            title="Old close",
            body="",
            created=datetime(2026, 1, 1, tzinfo=UTC),
            closed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        newest = Ticket(
            id="new1",
            status="closed",
            title="New close",
            body="",
            created=datetime(2026, 1, 1, tzinfo=UTC),
            closed_at=datetime(2026, 1, 4, tzinfo=UTC),
        )
        middle = Ticket(
            id="mid1",
            status="closed",
            title="Middle close",
            body="",
            created=datetime(2026, 1, 1, tzinfo=UTC),
            closed_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        write_ticket(oldest, tickets_dir / "old1.md")
        write_ticket(newest, tickets_dir / "new1.md")
        write_ticket(middle, tickets_dir / "mid1.md")

        result = runner.invoke(ticket_app, ["list", "--recently-closed"])

        assert result.exit_code == 0, result.output
        assert result.output.index("new1") < result.output.index("mid1") < result.output.index("old1")
        assert "3 closed" in result.output

    def test_recently_closed_limit(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        for index in range(3):
            ticket_id = f"tk{index}"
            write_ticket(
                Ticket(
                    id=ticket_id,
                    status="closed",
                    title=f"Closed {index}",
                    body="",
                    created=datetime(2026, 1, 1, tzinfo=UTC),
                    closed_at=datetime(2026, 1, index + 1, tzinfo=UTC),
                ),
                tickets_dir / f"{ticket_id}.md",
            )

        result = runner.invoke(ticket_app, ["list", "--recently-closed", "--limit", "2"])

        assert result.exit_code == 0, result.output
        assert "tk2" in result.output
        assert "tk1" in result.output
        assert "tk0" not in result.output
        assert "2 total" in result.output

    def test_recently_closed_all_includes_archived_backlog(self, cli_project: Path) -> None:
        archive_dir = cli_project / ".kd" / "archive" / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        write_ticket(
            Ticket(
                id="arch",
                status="closed",
                title="Archived backlog close",
                body="",
                created=datetime(2026, 1, 1, tzinfo=UTC),
                closed_at=datetime(2026, 1, 5, tzinfo=UTC),
            ),
            archive_dir / "arch.md",
        )

        result = runner.invoke(ticket_app, ["list", "--all", "--recently-closed"])

        assert result.exit_code == 0, result.output
        assert "arch" in result.output
        assert "archive:backlog" in result.output

    def test_recently_closed_backlog_json_labels_archived_backlog(self, cli_project: Path) -> None:
        archive_dir = cli_project / ".kd" / "archive" / "backlog" / "tickets"
        archive_dir.mkdir(parents=True, exist_ok=True)
        write_ticket(
            Ticket(
                id="arch",
                status="closed",
                title="Archived backlog close",
                body="",
                created=datetime(2026, 1, 1, tzinfo=UTC),
                closed_at=datetime(2026, 1, 5, tzinfo=UTC),
            ),
            archive_dir / "arch.md",
        )

        result = runner.invoke(ticket_app, ["list", "--backlog", "--recently-closed", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data[0]["id"] == "arch"
        assert data[0]["location"] == "archive:backlog"


class TestTicketListPriority:
    def test_priority_filter_branch(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        p1 = Ticket(id="aaaa", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
        p2 = Ticket(id="bbbb", status="open", title="Normal", body="", priority=2, created=datetime.now(UTC))
        write_ticket(p1, tickets_dir / "aaaa.md")
        write_ticket(p2, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "-p", "1"])

        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output

    def test_priority_filter_backlog(self, cli_project: Path) -> None:
        backlog_dir = backlog_root(cli_project) / "tickets"
        backlog_dir.mkdir(parents=True, exist_ok=True)

        p1 = Ticket(id="aaaa", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
        p2 = Ticket(id="bbbb", status="open", title="Normal", body="", priority=2, created=datetime.now(UTC))
        write_ticket(p1, backlog_dir / "aaaa.md")
        write_ticket(p2, backlog_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--backlog", "-p", "1"])

        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output

    def test_summary_reflects_filter(self, cli_project: Path) -> None:
        """Summary line should count only filtered tickets, not all tickets."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        p1 = Ticket(id="aaaa", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
        p2 = Ticket(id="bbbb", status="open", title="Normal", body="", priority=2, created=datetime.now(UTC))
        p3 = Ticket(id="cccc", status="open", title="Also normal", body="", priority=2, created=datetime.now(UTC))
        write_ticket(p1, tickets_dir / "aaaa.md")
        write_ticket(p2, tickets_dir / "bbbb.md")
        write_ticket(p3, tickets_dir / "cccc.md")

        result = runner.invoke(ticket_app, ["list", "-p", "1"])

        assert result.exit_code == 0
        # Summary should say "1 open . 1 total", not "3 open . 3 total"
        assert "1 total" in result.output
        assert "3 total" not in result.output

    def test_priority_filter_invalid(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list", "-p", "5"])

        assert result.exit_code == 1
        assert "Invalid priority" in result.output


class TestTicketListTable:
    """Tests for Rich table formatting in tk list."""

    def test_table_has_header_row(self, cli_project: Path) -> None:
        """The table should include column headers."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="Test ticket", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "ID" in result.output
        assert "Status" in result.output
        assert "Title" in result.output

    def test_table_shows_priority(self, cli_project: Path) -> None:
        """Priority should be displayed as P1, P2, etc."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="High priority", body="", priority=1, created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "P1" in result.output

    def test_table_shows_assignee(self, cli_project: Path) -> None:
        """Assignee should be visible when set."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(
            id="aaaa", status="open", title="Assigned ticket", body="", assignee="alice", created=datetime.now(UTC)
        )
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "@alice" in result.output

    def test_table_shows_context_assignee_after_start(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(id="hand", status="open", title="Hand ticket", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "hand.md")

        with patch.dict(os.environ, {"KD_CONTEXT": "list-session"}, clear=True):
            start_result = runner.invoke(ticket_app, ["start", "hand"])
            assert start_result.exit_code == 0, start_result.output
            context = resolve_execution_context()
            result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0, result.output
        assert context is not None
        assert "hand" in result.output
        assert f"@{context.context_id}" in result.output

    def test_table_shows_deps(self, cli_project: Path) -> None:
        """Dependencies should be visible in the table."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(
            id="aaaa",
            status="open",
            title="Blocked ticket",
            body="",
            deps=["bbbb", "cccc"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "bbbb" in result.output
        assert "cccc" in result.output

    def test_table_shows_dep_status(self, cli_project: Path) -> None:
        """Closed deps should show checkmark, open deps should not."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        # Create a closed dep and an open dep
        closed_dep = Ticket(id="bbbb", status="closed", title="Done dep", body="", created=datetime.now(UTC))
        write_ticket(closed_dep, tickets_dir / "bbbb.md")

        open_dep = Ticket(id="cccc", status="open", title="Open dep", body="", created=datetime.now(UTC))
        write_ticket(open_dep, tickets_dir / "cccc.md")

        ticket = Ticket(
            id="aaaa",
            status="open",
            title="Has deps",
            body="",
            deps=["bbbb", "cccc"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--closed"])

        assert result.exit_code == 0
        # Closed dep should have checkmark
        assert "bbbb \u2713" in result.output
        # Open dep should NOT have checkmark
        assert "cccc \u2713" not in result.output
        assert "cccc" in result.output

    def test_table_shows_dep_status_include_done(self, cli_project: Path) -> None:
        """Deps in done branches should still show checkmark with --all --include-done."""
        from kingdom.state import write_json

        # Create a done branch with a closed dep ticket
        done_branch = ensure_branch_layout(cli_project, "done-branch")
        write_json(done_branch / "state.json", {"status": "done"})
        done_tickets = done_branch / "tickets"
        closed_dep = Ticket(id="dddd", status="closed", title="Done dep", body="", created=datetime.now(UTC))
        write_ticket(closed_dep, done_tickets / "dddd.md")

        # Create a ticket on the active branch that depends on the done-branch ticket
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        ticket = Ticket(
            id="eeee",
            status="open",
            title="Depends on done",
            body="",
            deps=["dddd"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "eeee.md")

        result = runner.invoke(ticket_app, ["list", "--all", "--include-done", "--closed"])

        assert result.exit_code == 0
        assert "dddd \u2713" in result.output

    def test_table_all_shows_location_column(self, cli_project: Path) -> None:
        """With --all flag, the Location column should be present."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="Branch ticket", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--all"])

        assert result.exit_code == 0
        assert "Location" in result.output
        assert "branch:" in result.output

    def test_table_backlog_no_location_column(self, cli_project: Path) -> None:
        """Without --all flag, no Location column should appear."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="Normal ticket", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "Location" not in result.output

    def test_table_hides_empty_assignee_and_deps_columns(self, cli_project: Path) -> None:
        """Assignee and Deps columns should be hidden when no ticket has data for them."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="No extras", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "Assignee" not in result.output
        assert "Deps" not in result.output

    def test_json_output_unaffected(self, cli_project: Path) -> None:
        """JSON output should not contain table formatting."""
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="JSON ticket", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "aaaa"
        assert data[0]["title"] == "JSON ticket"


class TestTicketListJson:
    """Tests for kd tk list --json."""

    def test_outputs_json(self, cli_project: Path) -> None:
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Test", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        result = runner.invoke(ticket_app, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "aaaa"
        # Full schema should include these fields
        assert "status" in data[0]
        assert "priority" in data[0]
        assert "type" in data[0]
        assert "created" in data[0]

    def test_json_excludes_closed_by_default(self, cli_project: Path) -> None:
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="closed", title="Closed", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Open", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "bbbb"

    def test_json_closed_includes_all(self, cli_project: Path) -> None:
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="closed", title="Closed", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Open", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--json", "--closed"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2


class TestTicketListFilters:
    """Tests for --assignee and --tag filters on list."""

    def test_filter_by_assignee(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Mine", body="", assignee="alice", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Theirs", body="", assignee="bob", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--assignee", "alice"])
        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output

    def test_filter_by_tag(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(
                id="aaaa",
                status="open",
                title="Frontend",
                body="",
                tags=["frontend"],
                created=datetime.now(UTC),
            ),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Backend", body="", tags=["backend"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--tag", "frontend"])
        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output


class TestTicketListDepsJson:
    """Tests for deps in JSON output of tk list."""

    def test_json_includes_deps_field(self, cli_project: Path) -> None:
        """JSON output should include deps array for each ticket."""
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(
            id="aaaa",
            status="open",
            title="Blocked",
            body="",
            deps=["bbbb", "cccc"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["deps"] == ["bbbb", "cccc"]

    def test_json_empty_deps_array(self, cli_project: Path) -> None:
        """Tickets with no deps should have empty deps array in JSON."""
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(id="aaaa", status="open", title="No deps", body="", created=datetime.now(UTC))
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["deps"] == []

    def test_json_all_includes_deps(self, cli_project: Path) -> None:
        """--all --json should include deps field."""
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        ticket = Ticket(
            id="aaaa",
            status="open",
            title="With deps",
            body="",
            deps=["xxxx"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, tickets_dir / "aaaa.md")

        result = runner.invoke(ticket_app, ["list", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        matching = [t for t in data if t["id"] == "aaaa"]
        assert len(matching) == 1
        assert matching[0]["deps"] == ["xxxx"]

    def test_json_backlog_includes_deps(self, cli_project: Path) -> None:
        """--backlog --json should include deps field."""
        import json

        backlog_dir = backlog_root(cli_project) / "tickets"

        ticket = Ticket(
            id="bbbb",
            status="open",
            title="Backlog with deps",
            body="",
            deps=["aaaa"],
            created=datetime.now(UTC),
        )
        write_ticket(ticket, backlog_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--backlog", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["deps"] == ["aaaa"]


class TestNoResultsMessages:
    """Tests for helpful empty-state messages with next-step guidance."""

    def test_list_empty_branch_shows_guidance(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list"])

        assert result.exit_code == 0
        assert "No tickets found" in result.output
        assert "kd tk create" in result.output

    def test_list_empty_backlog_shows_guidance(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list", "--backlog"])

        assert result.exit_code == 0
        assert "No backlog tickets" in result.output
        assert "kd tk create --backlog" in result.output

    def test_list_all_empty_shows_guidance(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list", "--all"])

        assert result.exit_code == 0
        assert "No tickets found" in result.output
        assert "kd tk create" in result.output

    def test_ready_empty_shows_no_tickets(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list", "--ready"])

        assert result.exit_code == 0
        assert "No tickets found" in result.output

    def test_ready_excludes_in_review(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        open_ticket = Ticket(id="aaaa", status="open", title="Open ticket", body="", created=datetime.now(UTC))
        review_ticket = Ticket(id="bbbb", status="in_review", title="Review ticket", body="", created=datetime.now(UTC))
        write_ticket(open_ticket, tickets_dir / "aaaa.md")
        write_ticket(review_ticket, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--ready"])

        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output

    def test_ready_filters_with_all(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        backlog_dir = backlog_root(cli_project) / "tickets"
        backlog_dir.mkdir(parents=True, exist_ok=True)

        branch_tk = Ticket(id="aaaa", status="open", title="Branch task", body="", created=datetime.now(UTC))
        backlog_tk = Ticket(id="bbbb", status="open", title="Backlog task", body="", created=datetime.now(UTC))
        write_ticket(branch_tk, tickets_dir / "aaaa.md")
        write_ticket(backlog_tk, backlog_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--ready", "--all"])

        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" in result.output

    def test_ready_excludes_blocked_tickets(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        blocker = Ticket(id="aaaa", status="open", title="Blocker", body="", created=datetime.now(UTC))
        blocked = Ticket(id="bbbb", status="open", title="Blocked", body="", deps=["aaaa"], created=datetime.now(UTC))
        write_ticket(blocker, tickets_dir / "aaaa.md")
        write_ticket(blocked, tickets_dir / "bbbb.md")

        result = runner.invoke(ticket_app, ["list", "--ready"])

        assert result.exit_code == 0
        assert "aaaa" in result.output
        assert "bbbb" not in result.output

    def test_show_all_empty_branch_shows_guidance(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["show", "--all"])

        assert result.exit_code == 0
        assert "No tickets on this branch" in result.output
        assert "kd tk create" in result.output


class TestFormatTicketLine:
    """Tests for the format_ticket_line helper."""

    def test_basic_line_no_deps(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Fix bug", body="", created=datetime.now(UTC))
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][open] - Fix bug"

    def test_line_with_deps(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(
            id="ab12", status="open", title="Fix bug", body="", deps=["cd34", "ef56"], created=datetime.now(UTC)
        )
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][open] - Fix bug  <- cd34, ef56"

    def test_line_with_single_dep(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(
            id="ab12", status="in_progress", title="Work", body="", deps=["zz99"], created=datetime.now(UTC)
        )
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][in_progress] - Work  <- zz99"

    def test_line_with_location(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Task", body="", created=datetime.now(UTC))
        line = format_ticket_line(ticket, location="backlog")
        assert line == "ab12 [P2][open] - Task (backlog)"

    def test_line_with_deps_and_location(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Task", body="", deps=["cd34"], created=datetime.now(UTC))
        line = format_ticket_line(ticket, location="branch:main")
        assert line == "ab12 [P2][open] - Task (branch:main)  <- cd34"

    def test_line_with_assignee(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Task", body="", assignee="alice", created=datetime.now(UTC))
        line = format_ticket_line(ticket)
        assert line == "ab12 [P2][open] @alice - Task"

    def test_line_priority_1(self) -> None:
        from kingdom.cli.ticket import format_ticket_line

        ticket = Ticket(id="ab12", status="open", title="Urgent", body="", priority=1, created=datetime.now(UTC))
        line = format_ticket_line(ticket)
        assert line == "ab12 [P1][open] - Urgent"


class TestFormatTicketSummary:
    def test_all_statuses(self) -> None:
        tickets = [
            Ticket(id="a", status="open", title="", body="", created=datetime.now(UTC)),
            Ticket(id="b", status="open", title="", body="", created=datetime.now(UTC)),
            Ticket(id="c", status="in_progress", title="", body="", created=datetime.now(UTC)),
            Ticket(id="d", status="closed", title="", body="", created=datetime.now(UTC)),
        ]
        result = format_ticket_summary(tickets)
        assert result == "2 open \u00b7 1 in_progress \u00b7 1 closed \u00b7 4 total"

    def test_only_open(self) -> None:
        tickets = [
            Ticket(id="a", status="open", title="", body="", created=datetime.now(UTC)),
        ]
        result = format_ticket_summary(tickets)
        assert result == "1 open \u00b7 1 total"

    def test_empty_list(self) -> None:
        result = format_ticket_summary([])
        assert result == "0 total"

    def test_dict_input(self) -> None:
        tickets = [{"status": "open"}, {"status": "closed"}]
        result = format_ticket_summary(tickets)
        assert result == "1 open \u00b7 1 closed \u00b7 2 total"
