from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.state import (
    branch_root,
    ensure_branch_layout,
    list_execution_contexts,
    record_execution_ticket_context,
    resolve_execution_context,
    set_current_run,
)
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()


def record_test_context(
    base: Path,
    feature: str,
    ticket_id: str,
    session_id: str,
    *,
    now: datetime,
    role: str = "agent",
) -> str:
    with patch.dict(os.environ, {"KD_CONTEXT": session_id}, clear=True):
        context = resolve_execution_context(host="codex", role=role, cwd=base, now=now)
    assert context is not None
    record_execution_ticket_context(base, context, ticket_id, feature=feature)
    return context.context_id


def test_status_human_readable_no_tickets() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Branch:" in result.output
        assert "Tickets: 0 open, 0 in progress, 0 in review, 0 closed, 0 ready (0 total)" in result.output
        # These lines should NOT appear in simplified output
        assert "Design: present" not in result.output
        assert "Design: empty" not in result.output
        assert "Design: missing" not in result.output
        assert "Breakdown: present" not in result.output
        assert "Breakdown: empty" not in result.output
        assert "Breakdown: missing" not in result.output
        assert "\nReady:" not in result.output


def test_status_human_readable_with_tickets() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = branch_root(base, feature) / "tickets"

        write_ticket(Ticket(id="kin-0001", title="First", status="open"), tickets_dir / "kin-0001.md")
        write_ticket(Ticket(id="kin-0002", title="Second", status="in_progress"), tickets_dir / "kin-0002.md")
        write_ticket(Ticket(id="kin-0003", title="Third", status="closed"), tickets_dir / "kin-0003.md")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Tickets: 1 open, 1 in progress, 0 in review, 1 closed," in result.output
        assert "ready" in result.output
        assert "(3 total)" in result.output
        # No separate Ready line
        assert "\nReady:" not in result.output


def test_status_counts_in_review_separately() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = branch_root(base, feature) / "tickets"

        write_ticket(Ticket(id="kin-0001", title="First", status="open"), tickets_dir / "kin-0001.md")
        write_ticket(Ticket(id="kin-0002", title="Second", status="in_review"), tickets_dir / "kin-0002.md")
        write_ticket(Ticket(id="kin-0003", title="Third", status="closed"), tickets_dir / "kin-0003.md")

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "1 in review" in result.output

        # in_review ticket should NOT be counted as ready
        json_result = runner.invoke(app, ["status", "--json"])
        data = json.loads(json_result.output)
        assert data["tickets"]["in_review"] == 1
        assert data["ready_count"] == 1  # only the open ticket is ready


def test_status_json_still_includes_design_breakdown(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("KD_ROLE", raising=False)
    monkeypatch.delenv("KD_AGENT_NAME", raising=False)
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "design_status" in data
        assert "breakdown_status" in data
        assert data["role"] == "king"
        assert data["agent_name"] == ""
        assert data["assignments"] == {}


def test_status_human_readable_shows_assignments_section() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = branch_root(base, feature) / "tickets"

        write_ticket(
            Ticket(id="kin-0001", title="Assigned", status="open", assignee="hand"),
            tickets_dir / "kin-0001.md",
        )
        write_ticket(
            Ticket(id="kin-0002", title="Unassigned", status="open"),
            tickets_dir / "kin-0002.md",
        )

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Assignments:" in result.output
        assert "hand: kin-0001 [open] Assigned" in result.output
        assert "hand: kin-0002" not in result.output


def test_status_json_includes_identity_and_assignments() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = branch_root(base, feature) / "tickets"

        write_ticket(
            Ticket(id="kin-0001", title="Assigned to hand", status="open", assignee="hand"),
            tickets_dir / "kin-0001.md",
        )
        write_ticket(
            Ticket(id="kin-0002", title="Assigned to peasant", status="in_progress", assignee="peasant-kin-0002"),
            tickets_dir / "kin-0002.md",
        )

        result = runner.invoke(
            app,
            ["status", "--json"],
            env={"KD_ROLE": "hand", "KD_AGENT_NAME": "hand"},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data["role"] == "hand"
        assert data["agent_name"] == "hand"
        assert data["assignments"]["hand"] == ["kin-0001"]
        assert data["assignments"]["peasant-kin-0002"] == ["kin-0002"]


def test_status_json_includes_live_and_stale_execution_contexts() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        tickets_dir = branch_root(base, feature) / "tickets"
        now = datetime.now(UTC)

        live_id = record_test_context(base, feature, "live", "live-session", now=now, role="agent")
        stale_id = record_test_context(
            base,
            feature,
            "stale",
            "stale-session",
            now=now - timedelta(hours=25),
            role="subagent",
        )
        write_ticket(
            Ticket(id="live", title="Live work", status="in_progress", assignee=live_id, parent="epic1"),
            tickets_dir / "live.md",
        )
        write_ticket(
            Ticket(id="stale", title="Stale work", status="in_progress", assignee=stale_id),
            tickets_dir / "stale.md",
        )

        result = runner.invoke(app, ["status", "--json", "--stale-hours", "24"])

        assert result.exit_code == 0, result.output
        contexts = {context["ticket_id"]: context for context in json.loads(result.output)["contexts"]}
        assert contexts["live"]["host"] == "codex"
        assert contexts["live"]["role"] == "agent"
        assert contexts["live"]["epic"] == "epic1"
        assert contexts["live"]["stale"] is False
        assert contexts["stale"]["role"] == "subagent"
        assert contexts["stale"]["stale"] is True


def test_status_human_readable_shows_session_assignments() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        tickets_dir = branch_root(base, feature) / "tickets"
        now = datetime.now(UTC)
        context_id = record_test_context(base, feature, "ctx1", "status-session", now=now)
        write_ticket(
            Ticket(id="ctx1", title="Session work", status="in_progress", assignee=context_id),
            tickets_dir / "ctx1.md",
        )

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0, result.output
        assert "Sessions:" in result.output
        assert "codex" in result.output
        assert "agent" in result.output
        assert "ctx1 [in_progress] Session work" in result.output


def test_status_prune_stale_removes_only_stale_contexts() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        now = datetime.now(UTC)
        record_test_context(base, feature, "live", "live-session", now=now)
        record_test_context(base, feature, "stale", "stale-session", now=now - timedelta(days=2))

        result = runner.invoke(app, ["status", "--prune-stale", "--stale-hours", "24"])

        assert result.exit_code == 0, result.output
        assert "Pruned 1 stale execution context" in result.output
        contexts = list_execution_contexts(base, feature=feature, stale_after=timedelta(hours=24), now=now)
        assert [context["ticket_id"] for context in contexts] == ["live"]
