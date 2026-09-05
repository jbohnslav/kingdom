"""Colliding IDs must never pick an arbitrary file for reading or mutation."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.state import branch_root
from kingdom.ticket import Ticket, write_ticket

BRANCH = "feature/collisions"


@pytest.mark.parametrize("location", ["branches/other", "backlog", "archive/old"])
@pytest.mark.parametrize("ticket_id", ["2a", "2a92", "kin-2a92", "2A92"])
@pytest.mark.parametrize("command", [["find"], ["close"], ["defer", "--reason", "Move work"]])
def test_collision_lists_candidates_without_mutating(
    cli_project: Path, location: str, ticket_id: str, command: list[str]
) -> None:
    first = branch_root(cli_project, BRANCH) / "tickets" / "2a92.md"
    second = cli_project / ".kd" / location / "tickets" / "2a92.md"
    write_ticket(Ticket(id="2a92", status="open", title="Intended work"), first)
    write_ticket(Ticket(id="2a92", status="closed", title="Unrelated work"), second)
    before = {path: path.read_bytes() for path in (first, second)}

    result = CliRunner().invoke(ticket_app, [*command, ticket_id])

    assert result.exit_code == 1, result.output
    assert "matches multiple tickets" in result.output
    assert "Intended work" in result.output
    assert "Unrelated work" in result.output
    assert "branch:feature-collisions" in result.output
    assert location.split("/")[-1] in result.output
    assert all(path.read_bytes() == content for path, content in before.items())
