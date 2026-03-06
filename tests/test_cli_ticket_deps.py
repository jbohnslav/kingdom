"""Tests for kd tk deps (add, remove, tree, cycle) and --blocked filter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.state import branch_root
from kingdom.ticket import Ticket, find_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


class TestTicketDep:
    """Tests for kd tk dep — adding dependencies."""

    def test_dep_appends_not_overwrites(self, cli_project: Path) -> None:
        """Adding a second dep must preserve the first (append, not overwrite).

        Uses the exact IDs from the bug report: cf1a depends on 3642 then d869.
        """
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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
        result1 = runner.invoke(ticket_app, ["deps", "add", "cf1a", "3642"])
        assert result1.exit_code == 0, result1.output
        assert "now depends on" in result1.output

        # Second dep: cf1a depends on d869
        result2 = runner.invoke(ticket_app, ["deps", "add", "cf1a", "d869"])
        assert result2.exit_code == 0, result2.output
        assert "now depends on" in result2.output

        # Both deps must be present
        found = find_ticket(cli_project, "cf1a")
        assert found is not None
        ticket, _ = found
        assert "3642" in ticket.deps, f"First dep lost! deps={ticket.deps}"
        assert "d869" in ticket.deps, f"Second dep missing! deps={ticket.deps}"
        assert len(ticket.deps) == 2

    def test_dep_preserves_existing_deps_on_disk(self, cli_project: Path) -> None:
        """A ticket with pre-existing deps on disk must keep them when adding a new dep."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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
        found_before = find_ticket(cli_project, "cf1a")
        assert found_before is not None
        ticket_before, _ = found_before
        assert "3642" in ticket_before.deps, f"Dep lost after roundtrip! deps={ticket_before.deps}"

        # Add second dep via CLI
        result = runner.invoke(ticket_app, ["deps", "add", "cf1a", "d869"])
        assert result.exit_code == 0, result.output
        assert "now depends on" in result.output

        # Both deps must be present
        found = find_ticket(cli_project, "cf1a")
        assert found is not None
        ticket, _ = found
        assert "3642" in ticket.deps, f"First dep lost! deps={ticket.deps}"
        assert "d869" in ticket.deps, f"Second dep missing! deps={ticket.deps}"
        assert len(ticket.deps) == 2

    def test_dep_survives_status_change(self, cli_project: Path) -> None:
        """Deps must survive when ticket status changes between dep adds."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        for tid in ["cf1a", "aaaa", "bbbb"]:
            t = Ticket(id=tid, status="open", title=f"Ticket {tid}", body="", created=datetime.now(UTC))
            write_ticket(t, tickets_dir / f"{tid}.md")

        # Add first dep
        runner.invoke(ticket_app, ["deps", "add", "cf1a", "aaaa"])
        # Change status (rewrites ticket)
        runner.invoke(ticket_app, ["start", "cf1a"])
        # Add second dep
        runner.invoke(ticket_app, ["deps", "add", "cf1a", "bbbb"])

        found = find_ticket(cli_project, "cf1a")
        assert found is not None
        ticket, _ = found
        assert ticket.status == "in_progress"
        assert "aaaa" in ticket.deps, f"First dep lost after status change! deps={ticket.deps}"
        assert "bbbb" in ticket.deps, f"Second dep missing! deps={ticket.deps}"
        assert len(ticket.deps) == 2

    def test_dep_idempotent(self, cli_project: Path) -> None:
        """Adding the same dep twice should be a no-op the second time."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

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
        runner.invoke(ticket_app, ["deps", "add", "cf1a", "aaaa"])
        result = runner.invoke(ticket_app, ["deps", "add", "cf1a", "aaaa"])

        assert result.exit_code == 0
        assert "already depends on" in result.output

        found = find_ticket(cli_project, "cf1a")
        assert found is not None
        ticket, _ = found
        assert ticket.deps == ["aaaa"]

    def test_dep_not_found(self, cli_project: Path) -> None:
        """Adding a dep with a nonexistent ticket should error."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        t = Ticket(id="cf1a", status="open", title="Target", body="", created=datetime.now(UTC))
        write_ticket(t, tickets_dir / "cf1a.md")

        result = runner.invoke(ticket_app, ["deps", "add", "cf1a", "zzzz"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestTicketUndep:
    """Tests for kd tk undep — removing dependencies."""

    def test_undep_removes_dependency(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        t = Ticket(id="cf1a", status="open", title="Target", body="", deps=["aaaa"], created=datetime.now(UTC))
        write_ticket(t, tickets_dir / "cf1a.md")

        result = runner.invoke(ticket_app, ["deps", "remove", "cf1a", "aaaa"])

        assert result.exit_code == 0, result.output
        assert "removed dependency" in result.output
        found = find_ticket(cli_project, "cf1a")
        assert found is not None
        ticket, _ = found
        assert "aaaa" not in ticket.deps

    def test_undep_not_a_dep(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        t = Ticket(id="cf1a", status="open", title="Target", body="", created=datetime.now(UTC))
        write_ticket(t, tickets_dir / "cf1a.md")

        result = runner.invoke(ticket_app, ["deps", "remove", "cf1a", "zzzz"])

        assert result.exit_code == 1
        assert "does not depend on" in result.output

    def test_undep_partial_match(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        # Create the dep ticket so find_ticket can resolve "abcd" -> "abcd1234"
        dep = Ticket(id="abcd1234", status="open", title="Dep ticket", body="", created=datetime.now(UTC))
        write_ticket(dep, tickets_dir / "abcd1234.md")

        t = Ticket(id="cf1a", status="open", title="Target", body="", deps=["abcd1234"], created=datetime.now(UTC))
        write_ticket(t, tickets_dir / "cf1a.md")

        result = runner.invoke(ticket_app, ["deps", "remove", "cf1a", "abcd"])

        assert result.exit_code == 0, result.output
        assert "removed dependency" in result.output
        found = find_ticket(cli_project, "cf1a")
        assert found is not None
        ticket, _ = found
        assert ticket.deps == []

    def test_undep_resolves_via_find_ticket(self, cli_project: Path) -> None:
        """undep should use find_ticket() for ID resolution, not substring match."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        # Create tickets whose IDs share a common prefix
        for tid in ["ab01", "ab02", "cc03"]:
            t = Ticket(id=tid, status="open", title=f"Ticket {tid}", body="", created=datetime.now(UTC))
            write_ticket(t, tickets_dir / f"{tid}.md")

        # Set up deps with both ab-prefixed tickets
        target = Ticket(
            id="cc03", status="open", title="Target", body="", deps=["ab01", "ab02"], created=datetime.now(UTC)
        )
        write_ticket(target, tickets_dir / "cc03.md")

        # "ab" is ambiguous — should error, not silently remove both
        result = runner.invoke(ticket_app, ["deps", "remove", "cc03", "ab"])
        # With proper resolution, this should fail as ambiguous
        assert result.exit_code == 1, f"Expected failure for ambiguous 'ab' but got: {result.output}"

        # Both deps should still be present
        found = find_ticket(cli_project, "cc03")
        assert found is not None
        ticket, _ = found
        assert len(ticket.deps) == 2, f"Expected 2 deps but got {ticket.deps}"

    def test_undep_preserves_other_deps(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"

        for tid in ["aaaa", "bbbb", "cccc"]:
            t = Ticket(id=tid, status="open", title=f"Ticket {tid}", body="", created=datetime.now(UTC))
            write_ticket(t, tickets_dir / f"{tid}.md")

        runner.invoke(ticket_app, ["deps", "add", "aaaa", "bbbb"])
        runner.invoke(ticket_app, ["deps", "add", "aaaa", "cccc"])
        runner.invoke(ticket_app, ["deps", "remove", "aaaa", "bbbb"])

        found = find_ticket(cli_project, "aaaa")
        assert found is not None
        ticket, _ = found
        assert ticket.deps == ["cccc"]


class TestTicketDepTree:
    """Tests for kd tk dep-tree."""

    def test_tree_shows_deps(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Root", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Dep", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["deps", "tree", "aaaa"])
        assert result.exit_code == 0
        assert "Root" in result.output
        assert "bbbb" in result.output
        assert "Dep" in result.output

    def test_tree_deduplicates_by_default(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Root", body="", deps=["bbbb", "cccc"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="B", body="", deps=["cccc"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        write_ticket(
            Ticket(id="cccc", status="open", title="C", body="", created=datetime.now(UTC)),
            tickets_dir / "cccc.md",
        )
        result = runner.invoke(ticket_app, ["deps", "tree", "aaaa"])
        assert result.exit_code == 0
        assert "see above" in result.output

    def test_tree_full_with_cycle_does_not_recurse_infinitely(self, cli_project: Path) -> None:
        """dep-tree --full should detect cycles instead of infinite recursion."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        # A -> B -> A (cycle)
        write_ticket(
            Ticket(id="aaaa", status="open", title="A", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="B", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["deps", "tree", "--full", "aaaa"])
        assert result.exit_code == 0
        assert "cycle" in result.output


class TestTicketDepCycle:
    """Tests for kd tk dep-cycle."""

    def test_no_cycles(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="A", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="B", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["deps", "cycle"])
        assert result.exit_code == 0
        assert "No dependency cycles" in result.output

    def test_detects_cycle(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="A", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="B", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["deps", "cycle"])
        assert result.exit_code == 1
        assert "cycle" in result.output.lower()

    def test_ignores_closed_ticket_cycles(self, cli_project: Path) -> None:
        """dep-cycle should not report cycles involving only closed tickets."""
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        # A -> B -> A cycle, but both are closed
        write_ticket(
            Ticket(id="aaaa", status="closed", title="A", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="closed", title="B", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["deps", "cycle"])
        assert result.exit_code == 0
        assert "No dependency cycles" in result.output


class TestTicketDepTreeJson:
    """Tests for kd tk deps tree --json."""

    def test_tree_json_outputs_valid_json(self, cli_project: Path) -> None:
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Root", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="in_progress", title="Dep", body="", created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )

        result = runner.invoke(ticket_app, ["deps", "tree", "--json", "aaaa"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "aaaa"
        assert data["status"] == "open"
        assert data["title"] == "Root"
        assert len(data["deps"]) == 1
        assert data["deps"][0]["id"] == "bbbb"
        assert data["deps"][0]["status"] == "in_progress"
        assert data["deps"][0]["title"] == "Dep"

    def test_tree_json_with_cycle(self, cli_project: Path) -> None:
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="A", body="", deps=["bbbb"], created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="B", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )

        result = runner.invoke(ticket_app, ["deps", "tree", "--json", "--full", "aaaa"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["deps"][0]["id"] == "bbbb"
        # The cycle back to aaaa should be flagged
        cycle_node = data["deps"][0]["deps"][0]
        assert cycle_node["id"] == "aaaa"
        assert cycle_node.get("cycle") is True

    def test_tree_json_no_deps(self, cli_project: Path) -> None:
        import json

        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Leaf", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )

        result = runner.invoke(ticket_app, ["deps", "tree", "--json", "aaaa"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "aaaa"
        assert "deps" not in data  # No deps key when ticket has no deps


class TestTicketBlocked:
    """Tests for kd tk list --blocked."""

    def test_lists_blocked_tickets(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="open", title="Blocker", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Blocked", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--blocked"])
        assert result.exit_code == 0
        assert "bbbb" in result.output
        # aaaa shows in deps column but should appear only once (as dep, not as its own row)
        assert "Blocker" not in result.output  # blocker ticket title should not appear

    def test_no_blocked_when_deps_closed(self, cli_project: Path) -> None:
        tickets_dir = branch_root(cli_project, BRANCH) / "tickets"
        write_ticket(
            Ticket(id="aaaa", status="closed", title="Done", body="", created=datetime.now(UTC)),
            tickets_dir / "aaaa.md",
        )
        write_ticket(
            Ticket(id="bbbb", status="open", title="Ready", body="", deps=["aaaa"], created=datetime.now(UTC)),
            tickets_dir / "bbbb.md",
        )
        result = runner.invoke(ticket_app, ["list", "--blocked"])
        assert result.exit_code == 0
        assert "No tickets found" in result.output
