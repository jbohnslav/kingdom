"""Ticket creation makes its destination explicit without switching context."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.state import backlog_root, branch_root, ensure_branch_layout, resolve_current_run
from kingdom.ticket import read_ticket

BRANCH = "feature/current-board"
runner = CliRunner()


def test_creation_labels_current_board(cli_project: Path) -> None:
    result = runner.invoke(ticket_app, ["create", "Current work"])
    assert result.exit_code == 0, result.output
    assert "(branch:feature-current-board)" in result.output.splitlines()[0]
    assert Path(result.output.splitlines()[-1]).parent == branch_root(cli_project, BRANCH) / "tickets"


def test_creation_on_explicit_board_preserves_current_context(cli_project: Path) -> None:
    target = "feature/other-board"
    ensure_branch_layout(cli_project, target)
    current = resolve_current_run(cli_project)
    result = runner.invoke(ticket_app, ["create", "Other work", "--branch", target])
    assert result.exit_code == 0, result.output
    assert "(branch:feature-other-board)" in result.output.splitlines()[0]
    path = Path(result.output.splitlines()[-1])
    assert path.parent == branch_root(cli_project, target) / "tickets"
    assert read_ticket(path).title == "Other work"
    assert not list((branch_root(cli_project, BRANCH) / "tickets").glob("*.md"))
    assert resolve_current_run(cli_project) == current


@pytest.mark.parametrize("args", [["--branch", "missing"], ["--branch", "///"], ["--branch", BRANCH, "--backlog"]])
def test_invalid_destination_does_not_create_tickets(cli_project: Path, args: list[str]) -> None:
    result = runner.invoke(ticket_app, ["create", "Invalid work", *args])
    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert not list((cli_project / ".kd").glob("**/tickets/*.md"))
    assert not branch_root(cli_project, "missing").exists()


def test_implicit_backlog_fallback_is_labeled(cli_project: Path) -> None:
    with patch("kingdom.cli.ticket.resolve_current_run", side_effect=RuntimeError("No workspace")):
        result = runner.invoke(ticket_app, ["create", "Later work"])
    assert result.exit_code == 0, result.output
    assert "(backlog)" in result.output.splitlines()[0]
    assert Path(result.output.splitlines()[-1]).parent == backlog_root(cli_project) / "tickets"
