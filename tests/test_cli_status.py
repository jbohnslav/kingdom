from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import ensure_run_layout, set_current_run
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()


def test_status_human_readable_no_tickets() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["status"])
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
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = base / ".kd" / "runs" / feature / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)

        write_ticket(Ticket(id="kin-0001", title="First", status="open"), tickets_dir / "kin-0001.md")
        write_ticket(Ticket(id="kin-0002", title="Second", status="in_progress"), tickets_dir / "kin-0002.md")
        write_ticket(Ticket(id="kin-0003", title="Third", status="closed"), tickets_dir / "kin-0003.md")

        result = runner.invoke(cli.app, ["status"])
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
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = base / ".kd" / "runs" / feature / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)

        write_ticket(Ticket(id="kin-0001", title="First", status="open"), tickets_dir / "kin-0001.md")
        write_ticket(Ticket(id="kin-0002", title="Second", status="in_review"), tickets_dir / "kin-0002.md")
        write_ticket(Ticket(id="kin-0003", title="Third", status="closed"), tickets_dir / "kin-0003.md")

        result = runner.invoke(cli.app, ["status"])
        assert result.exit_code == 0
        assert "1 in review" in result.output

        # in_review ticket should NOT be counted as ready
        json_result = runner.invoke(cli.app, ["status", "--json"])
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
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["status", "--json"])
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
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = base / ".kd" / "runs" / feature / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)

        write_ticket(
            Ticket(id="kin-0001", title="Assigned", status="open", assignee="hand"),
            tickets_dir / "kin-0001.md",
        )
        write_ticket(
            Ticket(id="kin-0002", title="Unassigned", status="open"),
            tickets_dir / "kin-0002.md",
        )

        result = runner.invoke(cli.app, ["status"])
        assert result.exit_code == 0
        assert "Assignments:" in result.output
        assert "hand: kin-0001 [open] Assigned" in result.output
        assert "hand: kin-0002" not in result.output


def test_status_json_includes_identity_and_assignments() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        tickets_dir = base / ".kd" / "runs" / feature / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)

        write_ticket(
            Ticket(id="kin-0001", title="Assigned to hand", status="open", assignee="hand"),
            tickets_dir / "kin-0001.md",
        )
        write_ticket(
            Ticket(id="kin-0002", title="Assigned to peasant", status="in_progress", assignee="peasant-kin-0002"),
            tickets_dir / "kin-0002.md",
        )

        result = runner.invoke(
            cli.app,
            ["status", "--json"],
            env={"KD_ROLE": "hand", "KD_AGENT_NAME": "hand"},
        )
        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data["role"] == "hand"
        assert data["agent_name"] == "hand"
        assert data["assignments"]["hand"] == ["kin-0001"]
        assert data["assignments"]["peasant-kin-0002"] == ["kin-0002"]
