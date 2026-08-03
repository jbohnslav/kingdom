from __future__ import annotations

import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli.ticket import migrate_ticket_to_execution_context, ticket_app
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
    backup = tmp_path / "kd-backup"
    shutil.copytree(base / ".kd", backup)
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

    (base / ".kd").rename(base / ".kd-upgraded")
    shutil.copytree(backup, base / ".kd")
    assert ticket_bytes(base) == before_tickets
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


def test_ticket_write_failure_leaves_recoverable_context_binding(tmp_path: Path) -> None:
    base = copy_upgrade_fixture(tmp_path / "repository")
    active_path = base / ".kd" / "branches" / "feature-upgrade" / "tickets" / "active1.md"
    original = active_path.read_bytes()

    with (
        patch.dict(os.environ, {"TERM_SESSION_ID": "upgrade-terminal"}, clear=True),
        patch("kingdom.state.Path.cwd", return_value=base),
    ):
        context = resolve_execution_context(cwd=base)
        assert context is not None
        with patch("kingdom.cli.ticket.write_ticket_content", side_effect=OSError("interrupted")):
            interrupted = runner.invoke(ticket_app, ["current", "--id"])
        binding = read_execution_ticket_context(base, context)
        after_interrupted = active_path.read_bytes()
        recovered = runner.invoke(ticket_app, ["current", "--id"])

    assert interrupted.exit_code == 1
    assert after_interrupted == original
    assert binding is not None
    assert binding["ticket_id"] == "active1"
    assert recovered.exit_code == 0
    assert recovered.output.strip() == "active1"
    assert active_path.read_bytes() == original.replace(b"assignee: hand", f"assignee: {context.context_id}".encode())


def test_concurrent_migrations_create_only_one_ticket_binding(tmp_path: Path) -> None:
    base = copy_upgrade_fixture(tmp_path / "repository")
    active_path = base / ".kd" / "branches" / "feature-upgrade" / "tickets" / "active1.md"
    with patch.dict(os.environ, {"KD_CONTEXT": "first"}, clear=True):
        first = resolve_execution_context(cwd=base)
    with patch.dict(os.environ, {"KD_CONTEXT": "second"}, clear=True):
        second = resolve_execution_context(cwd=base)
    assert first is not None
    assert second is not None

    barrier = threading.Barrier(2)

    def migrate(context):
        ticket = read_ticket(active_path)
        barrier.wait()
        return migrate_ticket_to_execution_context(
            base,
            context,
            ticket,
            active_path,
            feature="feature-upgrade",
            location="branch:feature-upgrade",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(migrate, (first, second)))

    bindings = [read_execution_ticket_context(base, context) for context in (first, second)]
    winner = read_ticket(active_path).assignee
    assert sum(result is not None for result in results) == 1
    assert sum(binding is not None for binding in bindings) == 1
    assert winner in {first.context_id, second.context_id}
    assert any(binding and binding["ticket_id"] == "active1" for binding in bindings)


def test_legacy_prefixed_ticket_filename_migrates_in_place(tmp_path: Path) -> None:
    base = copy_upgrade_fixture(tmp_path / "repository")
    tickets = base / ".kd" / "branches" / "feature-upgrade" / "tickets"
    ticket_path = tickets / "kin-active1.md"
    (tickets / "active1.md").rename(ticket_path)
    (base / ".kd" / "runtime" / "terminal-context" / "83219003ca25caba.json").unlink()

    with (
        patch.dict(os.environ, {"TERM_SESSION_ID": "upgrade-terminal"}, clear=True),
        patch("kingdom.state.Path.cwd", return_value=base),
    ):
        result = runner.invoke(ticket_app, ["current", "--id"])

    assert result.exit_code == 0
    assert result.output.strip() == "active1"
    assert ticket_path.exists()
    assert not (tickets / "active1.md").exists()
    assert read_ticket(ticket_path).assignee is not None
