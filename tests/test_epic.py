"""Tests for epic ticket support."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli.peasant import peasant_app
from kingdom.cli.ticket import ticket_app
from kingdom.state import branch_root, ensure_branch_layout, set_current_run
from kingdom.ticket import TICKET_TYPES, Ticket, find_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


def setup_project(base: Path) -> None:
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


def tickets_dir(base: Path) -> Path:
    return branch_root(base, BRANCH) / "tickets"


class TestTicketTypeValidation:
    def test_known_types_constant(self) -> None:
        assert {"task", "bug", "feature", "epic"} == TICKET_TYPES

    def test_create_with_valid_type(self, cli_project: Path) -> None:
        for t in ("task", "bug", "feature", "epic"):
            result = runner.invoke(ticket_app, ["create", f"{t} ticket", "-t", t])
            assert result.exit_code == 0, f"Failed for type {t}: {result.output}"

    def test_create_rejects_invalid_type(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "Bad type", "-t", "story"])
        assert result.exit_code == 1
        assert "Invalid type" in result.output
        assert "story" in result.output

    def test_edit_rejects_invalid_type(self, cli_project: Path) -> None:
        """Post-edit validation catches invalid type set via editor."""
        tdir = tickets_dir(cli_project)
        ticket = Ticket(id="ed01", status="open", title="Edit me", type="task", body="", created=datetime.now(UTC))
        write_ticket(ticket, tdir / "ed01.md")

        # Simulate editor changing type to an invalid value by writing directly
        content = (tdir / "ed01.md").read_text()
        (tdir / "ed01.md").write_text(content.replace("type: task", "type: story"))

        # Invoke edit with a no-op editor (cat) so the invalid type is read back
        result = runner.invoke(ticket_app, ["edit", "ed01"], env={"EDITOR": "true"})
        assert result.exit_code == 1
        assert "Invalid type" in result.output
        assert "story" in result.output

    def test_edit_accepts_valid_type(self, cli_project: Path) -> None:
        """Post-edit validation passes for valid types."""
        tdir = tickets_dir(cli_project)
        ticket = Ticket(id="ed02", status="open", title="Edit me", type="epic", body="", created=datetime.now(UTC))
        write_ticket(ticket, tdir / "ed02.md")

        result = runner.invoke(ticket_app, ["edit", "ed02"], env={"EDITOR": "true"})
        assert result.exit_code == 0

    def test_create_epic_type_persisted(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["create", "My epic", "-t", "epic"])
        assert result.exit_code == 0
        ticket_id = result.output.strip().split(":")[0].replace("Created ", "")
        found = find_ticket(cli_project, ticket_id)
        assert found is not None
        assert found.ticket.type == "epic"


class TestListParentFilter:
    def test_list_parent_shows_children(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        parent = Ticket(id="epic1", status="open", title="The Epic", type="epic", body="", created=datetime.now(UTC))
        child1 = Ticket(id="ch01", status="open", title="Child one", body="", parent="epic1", created=datetime.now(UTC))
        child2 = Ticket(
            id="ch02", status="closed", title="Child two", body="", parent="epic1", created=datetime.now(UTC)
        )
        unrelated = Ticket(id="oth1", status="open", title="Unrelated", body="", created=datetime.now(UTC))
        for t in (parent, child1, child2, unrelated):
            write_ticket(t, tdir / f"{t.id}.md")

        result = runner.invoke(ticket_app, ["list", "--parent", "epic1", "--closed"])
        assert result.exit_code == 0, result.output
        assert "ch01" in result.output
        assert "ch02" in result.output
        assert "oth1" not in result.output
        assert "epic1" not in result.output  # parent itself excluded

    def test_list_parent_not_found(self, cli_project: Path) -> None:
        result = runner.invoke(ticket_app, ["list", "--parent", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestShowChildRollup:
    def test_show_displays_child_rollup(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        parent = Ticket(id="epic2", status="open", title="Parent Epic", type="epic", body="", created=datetime.now(UTC))
        child1 = Ticket(
            id="ch03", status="closed", title="Done child", body="", parent="epic2", created=datetime.now(UTC)
        )
        child2 = Ticket(
            id="ch04", status="open", title="Open child", body="", parent="epic2", created=datetime.now(UTC)
        )
        child3 = Ticket(
            id="ch05", status="closed", title="Also done", body="", parent="epic2", created=datetime.now(UTC)
        )
        for t in (parent, child1, child2, child3):
            write_ticket(t, tdir / f"{t.id}.md")

        result = runner.invoke(ticket_app, ["show", "epic2", "--rich"])
        assert result.exit_code == 0, result.output
        assert "2/3 closed" in result.output

    def test_show_no_children_no_rollup(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        ticket = Ticket(id="lone1", status="open", title="No kids", body="", created=datetime.now(UTC))
        write_ticket(ticket, tdir / "lone1.md")

        result = runner.invoke(ticket_app, ["show", "lone1"])
        assert result.exit_code == 0
        assert "Children" not in result.output


class TestPeasantEpicGuard:
    def test_start_rejects_epic_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tdir = base / ".kd" / "branches" / "feature-ticket-test" / "tickets"
            tdir.mkdir(parents=True, exist_ok=True)
            epic = Ticket(
                id="kin-epc1", status="open", title="Epic ticket", type="epic", body="", created=datetime.now(UTC)
            )
            write_ticket(epic, tdir / "kin-epc1.md")

            result = runner.invoke(peasant_app, ["start", "kin-epc1"])
            assert result.exit_code == 1
            assert "epic" in result.output.lower()
            assert "atomic" in result.output.lower() or "not atomic" in result.output.lower()

    def test_start_allows_non_epic_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tdir = base / ".kd" / "branches" / "feature-ticket-test" / "tickets"
            tdir.mkdir(parents=True, exist_ok=True)
            task = Ticket(
                id="kin-tsk1", status="open", title="Task ticket", type="task", body="", created=datetime.now(UTC)
            )
            write_ticket(task, tdir / "kin-tsk1.md")

            with patch("kingdom.cli.launch_work_background", return_value=12345):
                result = runner.invoke(peasant_app, ["start", "kin-tsk1", "--hand"])
            assert result.exit_code == 0, result.output


class TestCloseEpicGuard:
    def test_close_epic_blocked_by_open_children(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        epic = Ticket(id="epic3", status="open", title="My Epic", type="epic", body="", created=datetime.now(UTC))
        child_open = Ticket(
            id="ch06", status="in_progress", title="Still working", body="", parent="epic3", created=datetime.now(UTC)
        )
        child_closed = Ticket(
            id="ch07", status="closed", title="Already done", body="", parent="epic3", created=datetime.now(UTC)
        )
        for t in (epic, child_open, child_closed):
            write_ticket(t, tdir / f"{t.id}.md")

        result = runner.invoke(ticket_app, ["close", "epic3"])
        assert result.exit_code == 1
        assert "open" in result.output.lower()
        assert "ch06" in result.output

    def test_close_epic_allowed_when_all_children_closed(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        epic = Ticket(id="epic4", status="open", title="Closable Epic", type="epic", body="", created=datetime.now(UTC))
        child1 = Ticket(id="ch08", status="closed", title="Done 1", body="", parent="epic4", created=datetime.now(UTC))
        child2 = Ticket(id="ch09", status="closed", title="Done 2", body="", parent="epic4", created=datetime.now(UTC))
        for t in (epic, child1, child2):
            write_ticket(t, tdir / f"{t.id}.md")

        result = runner.invoke(ticket_app, ["close", "epic4"])
        assert result.exit_code == 0
        assert "closed" in result.output.lower()

    def test_close_epic_no_children_allowed(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        epic = Ticket(id="epic5", status="open", title="Empty Epic", type="epic", body="", created=datetime.now(UTC))
        write_ticket(epic, tdir / "epic5.md")

        result = runner.invoke(ticket_app, ["close", "epic5"])
        assert result.exit_code == 0

    def test_close_non_epic_with_open_children_allowed(self, cli_project: Path) -> None:
        """Non-epic tickets with children don't get the close guard."""
        tdir = tickets_dir(cli_project)
        parent = Ticket(
            id="feat1", status="open", title="Feature parent", type="feature", body="", created=datetime.now(UTC)
        )
        child = Ticket(id="ch10", status="open", title="Open child", body="", parent="feat1", created=datetime.now(UTC))
        for t in (parent, child):
            write_ticket(t, tdir / f"{t.id}.md")

        result = runner.invoke(ticket_app, ["close", "feat1"])
        assert result.exit_code == 0


class TestListEpicBadge:
    def test_list_shows_epic_badge(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        epic = Ticket(id="epic6", status="open", title="Badge Epic", type="epic", body="", created=datetime.now(UTC))
        task = Ticket(id="tsk2", status="open", title="Normal task", type="task", body="", created=datetime.now(UTC))
        for t in (epic, task):
            write_ticket(t, tdir / f"{t.id}.md")

        result = runner.invoke(ticket_app, ["list"])
        assert result.exit_code == 0
        assert "[epic]" in result.output
        # The badge should be near the epic title, not the task
        lines = result.output.split("\n")
        for line in lines:
            if "Normal task" in line:
                assert "[epic]" not in line
            if "Badge Epic" in line:
                assert "[epic]" in line
