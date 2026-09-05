"""End-to-end coverage for several execution contexts sharing one branch."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.ticket import ticket_app
from kingdom.state import (
    branch_root,
    ensure_branch_layout,
    execution_context_path,
    resolve_execution_context,
    set_current_run,
    write_json,
)
from kingdom.ticket import Ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/concurrent-contexts"


def setup_project(base: Path, ticket_ids: list[str]) -> Path:
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)
    tickets_dir = branch_root(base, BRANCH) / "tickets"
    for ticket_id in ticket_ids:
        write_ticket(
            Ticket(
                id=ticket_id,
                status="open",
                title=f"Work for {ticket_id}",
                body="",
                created=datetime.now(UTC),
            ),
            tickets_dir / f"{ticket_id}.md",
        )
    return tickets_dir


def test_five_contexts_keep_current_log_status_and_close_isolated() -> None:
    identities = [
        {"KD_CONTEXT": "alpha", "KD_ROLE": "agent"},
        {"KD_CONTEXT": "bravo", "KD_ROLE": "subagent"},
        {"KD_CONTEXT": "charlie", "KD_ROLE": "agent"},
        {"CODEX_THREAD_ID": "codex-delta", "KD_ROLE": "subagent"},
        {"TERM_SESSION_ID": "terminal-echo", "KD_ROLE": "agent"},
    ]
    ticket_ids = ["ctx1", "ctx2", "ctx3", "ctx4", "ctx5"]

    with runner.isolated_filesystem():
        base = Path.cwd()
        tickets_dir = setup_project(base, ticket_ids)

        for environment, ticket_id in zip(identities, ticket_ids, strict=True):
            with patch.dict(os.environ, environment, clear=True):
                result = runner.invoke(ticket_app, ["start", ticket_id])
            assert result.exit_code == 0, result.output

        for index, (environment, ticket_id) in enumerate(zip(identities, ticket_ids, strict=True), start=1):
            with patch.dict(os.environ, environment, clear=True):
                current = runner.invoke(ticket_app, ["current", "--id"])
                assert current.output.strip() == ticket_id
                log_result = runner.invoke(
                    ticket_app,
                    ["log", current.output.strip(), f"context-{index} wrote here"],
                )
            assert log_result.exit_code == 0, log_result.output

        for index, ticket_id in enumerate(ticket_ids, start=1):
            content = (tickets_dir / f"{ticket_id}.md").read_text(encoding="utf-8")
            assert f"context-{index} wrote here" in content
            for other_index in set(range(1, 6)) - {index}:
                assert f"context-{other_index} wrote here" not in content

        status_result = runner.invoke(app, ["status", "--json"])
        assert status_result.exit_code == 0, status_result.output
        status_contexts = json.loads(status_result.output)["contexts"]
        contexts_by_ticket = {context["ticket_id"]: context for context in status_contexts}
        assert set(contexts_by_ticket) == set(ticket_ids)
        assert len({context["context_id"] for context in status_contexts}) == 5
        assert {context["host"] for context in status_contexts} == {"kingdom", "codex", "terminal"}

        remaining = set(ticket_ids)
        for environment, ticket_id in zip(identities, ticket_ids, strict=True):
            with patch.dict(os.environ, environment, clear=True):
                close_result = runner.invoke(ticket_app, ["close", ticket_id, "--reason", "context finished"])
                ended_current = runner.invoke(ticket_app, ["current", "--id"])
            assert close_result.exit_code == 0, close_result.output
            assert ended_current.exit_code == 1

            remaining.remove(ticket_id)
            status_result = runner.invoke(app, ["status", "--json"])
            status_ticket_ids = {
                context["ticket_id"]
                for context in json.loads(status_result.output)["contexts"]
                if context["ticket_id"] is not None
            }
            assert status_ticket_ids == remaining

            for other_environment, other_ticket_id in zip(identities, ticket_ids, strict=True):
                if other_ticket_id not in remaining:
                    continue
                with patch.dict(os.environ, other_environment, clear=True):
                    current = runner.invoke(ticket_app, ["current", "--id"])
                assert current.output.strip() == other_ticket_id


def test_reused_terminal_switches_only_its_own_binding() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        tickets_dir = setup_project(base, ["old1", "next"])
        environment = {"TERM_SESSION_ID": "reused-terminal", "KD_ROLE": "agent"}

        with patch.dict(os.environ, environment, clear=True):
            first = runner.invoke(ticket_app, ["start", "old1"])
            second = runner.invoke(ticket_app, ["start", "next"])
            current = runner.invoke(ticket_app, ["current", "--id"])

        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        assert current.output.strip() == "next"
        assert read_ticket(tickets_dir / "old1.md").assignee is None
        assert (read_ticket(tickets_dir / "next.md").assignee or "").startswith("terminal:")


def test_pruned_stale_terminal_binding_cannot_resurrect() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        tickets_dir = setup_project(base, ["stale"])
        environment = {"TERM_SESSION_ID": "ended-terminal", "KD_ROLE": "agent"}

        with patch.dict(os.environ, environment, clear=True):
            start_result = runner.invoke(ticket_app, ["start", "stale"])
            context = resolve_execution_context()
        assert start_result.exit_code == 0, start_result.output
        assert context is not None

        context_path = execution_context_path(base, context)
        record = json.loads(context_path.read_text(encoding="utf-8"))
        record["last_seen"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        write_json(context_path, record)

        prune_result = runner.invoke(app, ["status", "--prune-stale", "--stale-hours", "24"])
        assert prune_result.exit_code == 0, prune_result.output
        assert "Pruned 1 stale execution context" in prune_result.output
        assert not context_path.exists()
        assert read_ticket(tickets_dir / "stale.md").status == "in_progress"

        with patch.dict(os.environ, environment, clear=True):
            current = runner.invoke(ticket_app, ["current", "--id"])
        assert current.exit_code == 1
