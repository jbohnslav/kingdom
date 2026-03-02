"""Tests for kd tk link / unlink commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import branch_root
from kingdom.ticket import Ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


class TestTicketLink:
    """Tests for kd tk link / unlink."""

    def test_link_creates_symmetric_links(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        for tid in ["aaaa", "bbbb"]:
            write_ticket(
                Ticket(id=tid, status="open", title=f"T {tid}", body="", created=datetime.now(UTC)),
                tickets_dir / f"{tid}.md",
            )
        result = runner.invoke(cli.app, ["tk", "link", "aaaa", "bbbb"])
        assert result.exit_code == 0
        assert "Linked" in result.output

        a = read_ticket(tickets_dir / "aaaa.md")
        b = read_ticket(tickets_dir / "bbbb.md")
        assert "bbbb" in a.links
        assert "aaaa" in b.links

    def test_unlink_removes_symmetric_links(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        for tid, links in [("aaaa", ["bbbb"]), ("bbbb", ["aaaa"])]:
            write_ticket(
                Ticket(id=tid, status="open", title=f"T {tid}", body="", links=links, created=datetime.now(UTC)),
                tickets_dir / f"{tid}.md",
            )
        result = runner.invoke(cli.app, ["tk", "unlink", "aaaa", "bbbb"])
        assert result.exit_code == 0
        assert "Unlinked" in result.output

        a = read_ticket(tickets_dir / "aaaa.md")
        b = read_ticket(tickets_dir / "bbbb.md")
        assert "bbbb" not in a.links
        assert "aaaa" not in b.links

    def test_link_needs_at_least_two(self, cli_project: Path) -> None:
        result = runner.invoke(cli.app, ["tk", "link", "aaaa"])
        assert result.exit_code == 1
        assert "at least two" in result.output

    def test_link_rejects_self_link(self, cli_project: Path) -> None:
        """kd tk link A A should reject self-links."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="T aaaa", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        result = runner.invoke(cli.app, ["tk", "link", "aaaa", "aaaa"])
        assert result.exit_code == 1
        assert "self-link" in result.output.lower() or "cannot link" in result.output.lower()

    def test_link_deduplicates_ids(self, cli_project: Path) -> None:
        """kd tk link A B A should deduplicate to just A <-> B."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        for tid in ["aaaa", "bbbb"]:
            write_ticket(
                Ticket(id=tid, status="open", title=f"T {tid}", body="", created=datetime.now(UTC)),
                tickets_dir / f"{tid}.md",
            )
        result = runner.invoke(cli.app, ["tk", "link", "aaaa", "bbbb", "aaaa"])
        assert result.exit_code == 0
        a = read_ticket(tickets_dir / "aaaa.md")
        # aaaa should link to bbbb only once, not to itself
        assert a.links.count("bbbb") == 1
        assert "aaaa" not in a.links
