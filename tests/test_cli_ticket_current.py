"""Tests for the `kd tk current` command."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli.ticket import ticket_app
from kingdom.state import (
    branch_root,
    ensure_branch_layout,
    execution_context_path,
    read_execution_ticket_context,
    read_terminal_ticket_context,
    record_terminal_ticket_context,
    resolve_execution_context,
    set_current_run,
    write_json,
)
from kingdom.ticket import Ticket, read_ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/ticket-test"


def setup_project(base: Path) -> None:
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


class TestTicketCurrent:
    def test_current_migration_completes_without_nested_ticket_lock_deadlock(self, tmp_path: Path) -> None:
        setup_project(tmp_path)
        ticket_path = branch_root(tmp_path, BRANCH) / "tickets" / "only.md"
        write_ticket(
            Ticket(
                id="only",
                status="in_progress",
                title="Only legacy ticket",
                assignee="hand",
                created=datetime.now(UTC),
            ),
            ticket_path,
        )
        source_root = Path(__file__).resolve().parent.parent / "src"
        env = os.environ.copy()
        env.update({"KD_BASE": str(tmp_path), "KD_CONTEXT": "migration-timeout", "PYTHONPATH": str(source_root)})

        result = subprocess.run(
            [sys.executable, "-c", "from kingdom.cli import main; main()", "ticket", "current", "--id"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=2,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "only"

    def test_current_migrates_exact_legacy_terminal_binding(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket_path = tickets_dir / "old1.md"
            write_ticket(
                Ticket(
                    id="old1",
                    status="in_progress",
                    title="Legacy terminal ticket",
                    body="",
                    assignee="hand",
                    created=datetime.now(UTC),
                ),
                ticket_path,
            )

            with patch.dict(os.environ, {"TERM_SESSION_ID": "legacy-terminal"}, clear=True):
                record_terminal_ticket_context(base, "old1", feature=BRANCH)
                legacy_before = read_terminal_ticket_context(base)
                first = runner.invoke(ticket_app, ["current", "--id"])
                second = runner.invoke(ticket_app, ["current", "--id"])
                context = resolve_execution_context()
                binding = read_execution_ticket_context(base, context)
                legacy_after = read_terminal_ticket_context(base)

            assert first.output.strip() == "old1"
            assert second.output.strip() == "old1"
            assert context is not None
            assert binding is not None
            assert binding["ticket_id"] == "old1"
            assert read_ticket(ticket_path).assignee == context.context_id
            assert legacy_after == legacy_before

    def test_current_migrates_single_branch_global_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket_path = tickets_dir / "only.md"
            write_ticket(
                Ticket(
                    id="only",
                    status="in_progress",
                    title="Only legacy ticket",
                    body="",
                    assignee="hand",
                    created=datetime.now(UTC),
                ),
                ticket_path,
            )

            with patch.dict(os.environ, {"KD_CONTEXT": "upgrade-session"}, clear=True):
                result = runner.invoke(ticket_app, ["current", "--id"])
                context = resolve_execution_context()
                binding = read_execution_ticket_context(base, context)

            assert result.output.strip() == "only"
            assert context is not None
            assert binding is not None
            assert read_ticket(ticket_path).assignee == context.context_id

    def test_current_refuses_ambiguous_branch_global_migration(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            for ticket_id in ("first", "second"):
                write_ticket(
                    Ticket(
                        id=ticket_id,
                        status="in_progress",
                        title=ticket_id,
                        body="",
                        assignee="hand",
                        created=datetime.now(UTC),
                    ),
                    tickets_dir / f"{ticket_id}.md",
                )

            with patch.dict(os.environ, {"KD_CONTEXT": "ambiguous-session"}, clear=True):
                result = runner.invoke(ticket_app, ["current"])
                context = resolve_execution_context()

            assert result.exit_code == 1
            assert "Multiple legacy in-progress tickets" in result.output
            assert "first" in result.output
            assert "second" in result.output
            assert context is not None
            assert read_execution_ticket_context(base, context) is None

    def test_current_recovers_partially_written_context_binding(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            write_ticket(
                Ticket(
                    id="part",
                    status="in_progress",
                    title="Partial migration",
                    body="",
                    assignee="hand",
                    created=datetime.now(UTC),
                ),
                tickets_dir / "part.md",
            )

            with patch.dict(os.environ, {"KD_CONTEXT": "partial-session"}, clear=True):
                context = resolve_execution_context()
                assert context is not None
                context_path = execution_context_path(base, context)
                context_path.parent.mkdir(parents=True)
                write_json(context_path, {"context_id": context.context_id, "ticket_id": None})

                result = runner.invoke(ticket_app, ["current", "--id"])
                binding = read_execution_ticket_context(base, context)

            assert result.output.strip() == "part"
            assert binding is not None
            assert binding["ticket_id"] == "part"

    def test_current_is_isolated_between_execution_contexts(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            write_ticket(
                Ticket(id="one1", status="open", title="First", body="", created=datetime.now(UTC)),
                tickets_dir / "one1.md",
            )
            write_ticket(
                Ticket(id="two2", status="open", title="Second", body="", created=datetime.now(UTC)),
                tickets_dir / "two2.md",
            )

            with patch.dict(os.environ, {"KD_CONTEXT": "session-one"}, clear=True):
                assert runner.invoke(ticket_app, ["start", "one1"]).exit_code == 0
            with patch.dict(os.environ, {"KD_CONTEXT": "session-two"}, clear=True):
                assert runner.invoke(ticket_app, ["start", "two2"]).exit_code == 0

            with patch.dict(os.environ, {"KD_CONTEXT": "session-one"}, clear=True):
                first = runner.invoke(ticket_app, ["current", "--id"])
            with patch.dict(os.environ, {"KD_CONTEXT": "session-two"}, clear=True):
                second = runner.invoke(ticket_app, ["current", "--id"])

            assert first.output.strip() == "one1"
            assert second.output.strip() == "two2"

    def test_current_does_not_guess_for_unbound_context(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            write_ticket(
                Ticket(
                    id="busy",
                    status="in_progress",
                    title="Someone else's",
                    body="",
                    assignee="codex:someone-else",
                    created=datetime.now(UTC),
                ),
                tickets_dir / "busy.md",
            )

            with patch.dict(os.environ, {"KD_CONTEXT": "unbound"}, clear=True):
                result = runner.invoke(ticket_app, ["current"])

            assert result.exit_code == 1
            assert "No ticket bound to this execution context" in result.output

    def test_start_uses_context_id_as_assignee(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            ticket_path = tickets_dir / "ctx1.md"
            write_ticket(
                Ticket(id="ctx1", status="open", title="Context", body="", created=datetime.now(UTC)),
                ticket_path,
            )

            with patch.dict(os.environ, {"KD_CONTEXT": "assigned-session"}, clear=True):
                result = runner.invoke(ticket_app, ["start", "ctx1"])
                context = resolve_execution_context()
                binding = read_execution_ticket_context(base, context)

            assert result.exit_code == 0, result.output
            assert context is not None
            assert binding is not None
            assert binding["ticket_id"] == "ctx1"
            assert read_ticket(ticket_path).assignee == context.context_id

    def test_branch_fallback_is_explicit(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"
            write_ticket(
                Ticket(id="low1", status="in_progress", title="Low", body="", priority=2, created=datetime.now(UTC)),
                tickets_dir / "low1.md",
            )
            write_ticket(
                Ticket(id="high", status="in_progress", title="High", body="", priority=1, created=datetime.now(UTC)),
                tickets_dir / "high.md",
            )

            with patch.dict(os.environ, {"KD_CONTEXT": "unbound"}, clear=True):
                result = runner.invoke(ticket_app, ["current", "--id", "--branch-fallback"])

            assert result.exit_code == 0, result.output
            assert result.output.strip() == "high"

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

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

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

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

            assert result.exit_code == 1
            assert "No in-progress ticket" in result.output

    def test_current_no_tickets_dir_exits_1(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

            assert result.exit_code == 1
            assert "No in-progress ticket" in result.output

    def test_current_no_project_root_exits_1(self) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(ticket_app, ["current"])

            assert result.exit_code == 1
            assert "No .kd/ directory found" in result.output

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

            result = runner.invoke(ticket_app, ["current", "--json", "--branch-fallback"])

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["id"] == "json1"
            assert data["status"] == "in_progress"
            assert data["title"] == "JSON test ticket"
            assert data["priority"] == 1
            assert data["type"] == "bug"

    def test_current_json_includes_context_assignee_after_start(self) -> None:
        with runner.isolated_filesystem():
            import json

            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            ticket = Ticket(
                id="hand",
                status="open",
                title="Hand ticket",
                body="",
                created=datetime.now(UTC),
            )
            write_ticket(ticket, tickets_dir / "hand.md")

            with patch.dict(os.environ, {"KD_CONTEXT": "json-session"}, clear=True):
                start_result = runner.invoke(ticket_app, ["start", "hand"])
                assert start_result.exit_code == 0, start_result.output
                context = resolve_execution_context()
                result = runner.invoke(ticket_app, ["current", "--json"])

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["id"] == "hand"
            assert context is not None
            assert data["assignee"] == context.context_id

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

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

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

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

            assert result.exit_code == 0, result.output
            assert "ip01" in result.output
            assert "The current one" in result.output
            # in_review ticket should not appear
            assert "rev1" not in result.output

    def test_exclude_peasant_skips_peasant_assigned(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            peasant_ticket = Ticket(
                id="pt01",
                status="in_progress",
                title="Peasant work",
                body="",
                assignee="peasant-pt01",
                created=datetime.now(UTC),
            )
            king_ticket = Ticket(
                id="kt01",
                status="in_progress",
                title="King work",
                body="",
                created=datetime.now(UTC),
            )
            write_ticket(peasant_ticket, tickets_dir / "pt01.md")
            write_ticket(king_ticket, tickets_dir / "kt01.md")

            result = runner.invoke(ticket_app, ["current", "--id", "--exclude-peasant", "--branch-fallback"])

            assert result.exit_code == 0, result.output
            assert "kt01" in result.output
            assert "pt01" not in result.output

    def test_exclude_peasant_no_nonpeasant_exits_1(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            peasant_ticket = Ticket(
                id="pt03",
                status="in_progress",
                title="Peasant work",
                body="",
                assignee="peasant-pt03",
                created=datetime.now(UTC),
            )
            write_ticket(peasant_ticket, tickets_dir / "pt03.md")

            result = runner.invoke(ticket_app, ["current", "--id", "--exclude-peasant", "--branch-fallback"])

            assert result.exit_code == 1

    def test_without_exclude_peasant_returns_peasant_ticket(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            peasant_ticket = Ticket(
                id="pt04",
                status="in_progress",
                title="Peasant work",
                body="",
                assignee="peasant-pt04",
                created=datetime.now(UTC),
            )
            write_ticket(peasant_ticket, tickets_dir / "pt04.md")

            result = runner.invoke(ticket_app, ["current", "--id", "--branch-fallback"])

            assert result.exit_code == 0, result.output
            assert "pt04" in result.output

    def test_current_only_in_review_exits_1(self) -> None:
        with runner.isolated_filesystem():
            base = Path.cwd()
            setup_project(base)
            tickets_dir = branch_root(base, BRANCH) / "tickets"

            review_ticket = Ticket(
                id="rev1", status="in_review", title="Under review", body="", created=datetime.now(UTC)
            )
            write_ticket(review_ticket, tickets_dir / "rev1.md")

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

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

            result = runner.invoke(ticket_app, ["current", "--branch-fallback"])

            assert result.exit_code == 0, result.output
            assert "ip01" in result.output
            assert "The current one" in result.output
