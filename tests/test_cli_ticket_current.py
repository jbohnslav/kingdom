"""Tests for the `kd tk current` command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import (
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


class TestTicketCurrent:
    def test_current_shows_in_progress_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="curr",
                status="in_progress",
                title="Working on this",
                body="Details",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "curr.md")

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 0, result.output
            assert "curr" in result.output
            assert "in_progress" in result.output
            assert "Working on this" in result.output

    def test_current_no_in_progress_exits_1(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="open1",
                status="open",
                title="Not started",
                body="",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "open1.md")

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 1
            assert "No in-progress ticket" in result.output

    def test_current_no_tickets_dir_exits_1(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 1
            assert "No in-progress ticket" in result.output

    def test_current_no_active_session_exits_1(self) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 1
            assert "No active session" in result.output

    def test_current_json_output(self) -> None:
        with runner.isolated_filesystem():
            import json

            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="json1",
                status="in_progress",
                title="JSON test ticket",
                body="Body here",
                priority=1,
                type="bug",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "json1.md")

            result = runner.invoke(cli.app, ["tk", "current", "--json"])

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["id"] == "json1"
            assert data["status"] == "in_progress"
            assert data["title"] == "JSON test ticket"
            assert data["priority"] == 1
            assert data["type"] == "bug"

    def test_current_picks_highest_priority(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            low = Ticket(
                id="low1",
                status="in_progress",
                title="Lower priority",
                body="",
                priority=2,
                created=datetime.now(UTC),
            )
            high = Ticket(
                id="high",
                status="in_progress",
                title="Higher priority",
                body="",
                priority=1,
                created=datetime.now(UTC),
            )
            write_ticket(low, tickets_dir / "low1.md")
            write_ticket(high, tickets_dir / "high.md")

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 0, result.output
            assert "high" in result.output
            assert "Higher priority" in result.output

    def test_current_ignores_in_review(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            review_ticket = Ticket(
                id="rev1", status="in_review", title="Under review", body="", created=datetime.now(UTC)
            )
            ip_ticket = Ticket(
                id="ip01", status="in_progress", title="The current one", body="", created=datetime.now(UTC)
            )
            write_ticket(review_ticket, tickets_dir / "rev1.md")
            write_ticket(ip_ticket, tickets_dir / "ip01.md")

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 0, result.output
            assert "ip01" in result.output
            assert "The current one" in result.output
            # in_review ticket should not appear
            assert "rev1" not in result.output

    def test_current_only_in_review_exits_1(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            review_ticket = Ticket(
                id="rev1", status="in_review", title="Under review", body="", created=datetime.now(UTC)
            )
            write_ticket(review_ticket, tickets_dir / "rev1.md")

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 1
            assert "No in-progress ticket" in result.output

    def test_current_ignores_closed_and_open(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            open_ticket = Ticket(id="op01", status="open", title="Open one", body="", created=datetime.now(UTC))
            closed_ticket = Ticket(id="cl01", status="closed", title="Closed one", body="", created=datetime.now(UTC))
            ip_ticket = Ticket(
                id="ip01", status="in_progress", title="The current one", body="", created=datetime.now(UTC)
            )
            write_ticket(open_ticket, tickets_dir / "op01.md")
            write_ticket(closed_ticket, tickets_dir / "cl01.md")
            write_ticket(ip_ticket, tickets_dir / "ip01.md")

            result = runner.invoke(cli.app, ["tk", "current"])

            assert result.exit_code == 0, result.output
            assert "ip01" in result.output
            assert "The current one" in result.output
