from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.state import (
    execution_context_path,
    read_execution_ticket_context,
    resolve_execution_context,
)
from kingdom.ticket import read_ticket

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "repository_upgrade" / "v0_6_mixed"


def copy_upgrade_fixture(destination: Path) -> Path:
    shutil.copytree(FIXTURE, destination, dirs_exist_ok=True)
    return destination


def ticket_bytes(base: Path) -> dict[str, bytes]:
    return {str(path.relative_to(base)): path.read_bytes() for path in sorted((base / ".kd").glob("**/tickets/*.md"))}


def test_mixed_repository_migration_preserves_ticket_content_and_legacy_rollback_state(tmp_path: Path) -> None:
    base = copy_upgrade_fixture(tmp_path / "repository")
    active_path = base / ".kd" / "branches" / "feature-upgrade" / "tickets" / "active1.md"
    legacy_path = base / ".kd" / "runtime" / "terminal-context" / "83219003ca25caba.json"
    before_tickets = ticket_bytes(base)
    before_active = active_path.read_text(encoding="utf-8")
    before_legacy = legacy_path.read_bytes()

    with (
        patch.dict(os.environ, {"TERM_SESSION_ID": "upgrade-terminal"}, clear=True),
        patch("kingdom.state.Path.cwd", return_value=base),
    ):
        context = resolve_execution_context(cwd=base)
        assert context is not None
        first = runner.invoke(ticket_app, ["current", "--id"])
        after_first = ticket_bytes(base)
        second = runner.invoke(ticket_app, ["current", "--id"])
        after_second = ticket_bytes(base)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert first.output.strip() == second.output.strip() == "active1"
    assert active_path.read_text(encoding="utf-8") == before_active.replace(
        "assignee: hand", f"assignee: {context.context_id}"
    )
    assert 'legacy-note: "preserve me exactly"' in active_path.read_text(encoding="utf-8")
    assert read_ticket(active_path).id == "active1"
    assert read_ticket(active_path).body.endswith("A durable note from the old repository.")

    unchanged_paths = set(before_tickets) - {".kd/branches/feature-upgrade/tickets/active1.md"}
    assert all(after_first[path] == before_tickets[path] for path in unchanged_paths)
    assert after_second == after_first
    assert legacy_path.read_bytes() == before_legacy

    generated_context = execution_context_path(base, context)
    generated_context.unlink()
    assert ticket_bytes(base) == after_second
    assert legacy_path.read_bytes() == before_legacy


def test_partial_context_write_recovers_without_rewriting_ticket(tmp_path: Path) -> None:
    base = copy_upgrade_fixture(tmp_path / "repository")
    active_path = base / ".kd" / "branches" / "feature-upgrade" / "tickets" / "active1.md"
    (base / ".kd" / "runtime" / "terminal-context" / "83219003ca25caba.json").unlink()

    with (
        patch.dict(os.environ, {"TERM_SESSION_ID": "upgrade-terminal"}, clear=True),
        patch("kingdom.state.Path.cwd", return_value=base),
    ):
        context = resolve_execution_context(cwd=base)
        assert context is not None
        active_path.write_text(
            active_path.read_text(encoding="utf-8").replace("assignee: hand", f"assignee: {context.context_id}"),
            encoding="utf-8",
        )
        before = active_path.read_bytes()
        context_path = execution_context_path(base, context)
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(json.dumps({"context_id": context.context_id, "ticket_id": None}), encoding="utf-8")

        result = runner.invoke(ticket_app, ["current", "--id"])
        binding = read_execution_ticket_context(base, context)

    assert result.exit_code == 0
    assert result.output.strip() == "active1"
    assert binding is not None
    assert binding["ticket_id"] == "active1"
    assert active_path.read_bytes() == before
