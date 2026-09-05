"""Branch relocation preserves ticket evidence and refuses unsafe moves."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.session import AgentState, set_agent_state
from kingdom.state import branch_root, ensure_branch_layout, resolve_current_run
from kingdom.ticket import Ticket, ticket_lock_path, write_ticket

BRANCH = "feature/move-source"
TARGET = "feature/move-target"
runner = CliRunner()


@pytest.mark.parametrize("status", ["open", "in_progress", "in_review", "closed"])
def test_move_preserves_entire_ticket(cli_project: Path, status: str) -> None:
    ensure_branch_layout(cli_project, TARGET)
    source = branch_root(cli_project, BRANCH) / "tickets" / "dbab.md"
    write_ticket(
        Ticket(
            id="dbab",
            status=status,
            title="Preserve evidence",
            assignee="Jim",
            parent="epic",
            deps=["dep1"],
            links=["link1"],
            closed_at=datetime(2026, 9, 1, tzinfo=UTC) if status == "closed" else None,
            resolution="completed" if status == "closed" else None,
            close_reason="Verified meaningful result" if status == "closed" else None,
            body="## Worklog\n\n- Original evidence",
        ),
        source,
    )
    source.write_bytes(
        source.read_bytes().replace(b"status:", b"custom-field: keep me\nstatus:").replace(b"\n", b"\r\n")
    )
    before = source.read_bytes()
    current = resolve_current_run(cli_project)

    result = runner.invoke(ticket_app, ["move", "dba", "--to-branch", TARGET])

    assert result.exit_code == 0, result.output
    destination = branch_root(cli_project, TARGET) / "tickets" / source.name
    assert destination.read_bytes() == before
    assert not source.exists()
    assert not ticket_lock_path(source).exists()
    assert ticket_lock_path(destination).exists()
    assert resolve_current_run(cli_project) == current
    assert "feature-move-source" in result.output
    assert "feature-move-target" in result.output
    assert "Preserve evidence" in result.output


def test_move_requires_existing_destination(cli_project: Path) -> None:
    source = branch_root(cli_project, BRANCH) / "tickets" / "dbab.md"
    write_ticket(Ticket(id="dbab", status="open", title="Stay put"), source)
    result = runner.invoke(ticket_app, ["move", "dbab", "--to-branch", "missing"])
    assert result.exit_code == 1, result.output
    assert "does not exist" in result.output
    assert source.exists()
    assert not branch_root(cli_project, "missing").exists()


def test_move_same_board_is_noop(cli_project: Path) -> None:
    source = branch_root(cli_project, BRANCH) / "tickets" / "dbab.md"
    write_ticket(Ticket(id="dbab", status="open", title="Stay put"), source)
    before = source.read_bytes()
    result = runner.invoke(ticket_app, ["move", "dbab", "--to-branch", BRANCH])
    assert result.exit_code == 0, result.output
    assert "already on branch" in result.output
    assert source.read_bytes() == before


@pytest.mark.parametrize("owner", ["native", "peasant"])
def test_move_refuses_active_workers(cli_project: Path, owner: str) -> None:
    ensure_branch_layout(cli_project, TARGET)
    source = branch_root(cli_project, BRANCH) / "tickets" / "dbab.md"
    assignee = "codex:active-session" if owner == "native" else "peasant-dbab"
    write_ticket(Ticket(id="dbab", status="in_progress", title="Active work", assignee=assignee), source)
    if owner == "peasant":
        set_agent_state(cli_project, BRANCH, assignee, AgentState(name=assignee, status="working", pid=99999))
    before = source.read_bytes()
    result = runner.invoke(ticket_app, ["move", "dbab", "--to-branch", TARGET])
    assert result.exit_code == 1, result.output
    assert "active" in result.output.lower()
    assert source.read_bytes() == before
    assert not (branch_root(cli_project, TARGET) / "tickets" / source.name).exists()


def test_move_rejects_duplicate_id_at_destination(cli_project: Path) -> None:
    ensure_branch_layout(cli_project, TARGET)
    paths = [branch_root(cli_project, branch) / "tickets" / "dbab.md" for branch in (BRANCH, TARGET)]
    for path in paths:
        write_ticket(Ticket(id="dbab", status="open", title=str(path.parent)), path)
    before = [path.read_bytes() for path in paths]
    result = runner.invoke(ticket_app, ["move", "dbab", "--to-branch", TARGET])
    assert result.exit_code == 1, result.output
    assert "matches multiple tickets" in result.output
    assert [path.read_bytes() for path in paths] == before


def test_move_rejects_invalid_branch_name(cli_project: Path) -> None:
    result = runner.invoke(ticket_app, ["move", "dbab", "--to-branch", "///"])
    assert result.exit_code == 1, result.output
    assert "normalizes to empty" in result.output
