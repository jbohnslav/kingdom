from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.state import (
    archive_root,
    branch_root,
    ensure_branch_layout,
    list_execution_contexts,
    record_execution_ticket_context,
    resolve_execution_context,
    set_current_run,
    write_json,
)
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()


def terminal_ticket_set() -> list[Ticket]:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Ticket(id="done", status="closed", title="Completed", resolution="completed", created=created),
        Ticket(
            id="nope",
            status="closed",
            title="Won't do",
            resolution="wont-do",
            close_reason="Out of scope",
            created=created,
        ),
        Ticket(
            id="dupe",
            status="closed",
            title="Duplicate",
            resolution="duplicate",
            close_reason="Same as done",
            duplicate_of="done",
            created=created,
        ),
        Ticket(
            id="old",
            status="closed",
            title="Superseded",
            resolution="superseded",
            close_reason="Replaced by done",
            superseded_by="done",
            created=created,
        ),
        Ticket(
            id="bad",
            status="closed",
            title="Invalid request",
            resolution="invalid",
            close_reason="Request cannot be reproduced",
            created=created,
        ),
    ]


def write_terminal_tickets(tickets_dir: Path, tickets: list[Ticket]) -> None:
    for ticket in tickets:
        write_ticket(ticket, tickets_dir / f"{ticket.id}.md")


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
        (branch_root(base, feature) / "design.md").write_text("# Optional design\n")

        result = runner.invoke(app, ["status", "--check"])
        assert result.exit_code == 0
        assert "Branch:" in result.output
        assert "Tickets: 0 open, 0 in progress, 0 in review, 0 closed, 0 ready (0 total)" in result.output
        assert "Optional design: .kd/branches/example-feature/design.md" in result.output
        assert result.output.index("Tickets:") < result.output.index("Optional design:")
        assert "Readiness: ready" in result.output
        assert "Breakdown:" not in result.output
        assert "\nReady:" not in result.output


def test_status_surfaces_git_and_kingdom_branch_mismatch() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        ensure_branch_layout(base, "previous-work")
        set_current_run(base, "previous-work")

        with (
            patch("kingdom.state.get_current_git_branch", return_value="new-work"),
            patch("kingdom.cli.get_current_git_branch", return_value="new-work"),
        ):
            human_result = runner.invoke(app, ["status"])
            json_result = runner.invoke(app, ["status", "--json"])

        assert human_result.exit_code == 0, human_result.output
        assert "Git branch 'new-work' does not match Kingdom workspace 'previous-work'." in human_result.output
        assert "Run `kd start -- new-work`" in human_result.output

        data = json.loads(json_result.output)
        assert data["git_branch"] == "new-work"
        assert data["branch_mismatch"] is True


@pytest.mark.parametrize(
    "git_branch",
    ["feature;true", "feature$(echo)", "feature`echo`", "feature'quote", "-leading"],
)
def test_status_suggests_literal_branch_argument(git_branch: str) -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        ensure_branch_layout(base, "previous-work")
        set_current_run(base, "previous-work")
        with (
            patch("kingdom.state.get_current_git_branch", return_value=git_branch),
            patch("kingdom.cli.get_current_git_branch", return_value=git_branch),
        ):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0, result.output
        line = next(line for line in result.output.splitlines() if line.startswith("Run `"))
        command = line.removeprefix("Run `").removesuffix("` to initialize or select this branch workspace.")
        # Capture argv through a harmless shell function to exercise actual
        # quoting, including command substitution and shell separators.
        captured = subprocess.run(
            ["sh", "-c", "kd() { printf '%s\\0' \"$@\"; }\n" + command],
            capture_output=True,
            check=True,
            timeout=5,
        )
        assert captured.stdout == b"start\0--\0" + git_branch.encode() + b"\0"


@pytest.mark.parametrize("git_branch", ["feature/example", None])
def test_status_does_not_report_false_branch_mismatch(git_branch: str | None) -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        ensure_branch_layout(base, "feature/example")
        set_current_run(base, "feature/example")

        with (
            patch("kingdom.state.get_current_git_branch", return_value=git_branch),
            patch("kingdom.cli.get_current_git_branch", return_value=git_branch),
        ):
            human_result = runner.invoke(app, ["status"])
            json_result = runner.invoke(app, ["status", "--json"])

        assert human_result.exit_code == 0, human_result.output
        assert "Warning:" not in human_result.output

        data = json.loads(json_result.output)
        assert data["git_branch"] == git_branch
        assert data["branch_mismatch"] is False


def test_status_help_describes_ticket_progress_and_concurrent_contexts() -> None:
    result = runner.invoke(app, ["status", "--help"])

    assert result.exit_code == 0
    assert "ticket progress and concurrent agent contexts" in result.output
    assert "design doc status" not in result.output
    assert "breakdown status" not in result.output


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
        assert "Readiness:" not in result.output
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


def test_status_shows_unassigned_ticket_after_leaving_in_progress() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        tickets_dir = ensure_branch_layout(base, feature) / "tickets"
        set_current_run(base, feature)
        write_ticket(
            Ticket(id="kin-blocked", title="Needs a decision", status="open"),
            tickets_dir / "kin-blocked.md",
        )

        with patch.dict(os.environ, {"KD_CONTEXT": "status-owner"}, clear=True):
            start_result = runner.invoke(app, ["tk", "start", "kin-blocked"])
            transition_result = runner.invoke(app, ["tk", "status", "kin-blocked", "blocked"])
            human_result = runner.invoke(app, ["status"])
            json_result = runner.invoke(app, ["status", "--json"])

        assert start_result.exit_code == 0, start_result.output
        assert transition_result.exit_code == 0, transition_result.output
        assert human_result.exit_code == 0, human_result.output
        assert "1 blocked" in human_result.output
        assert "Unassigned:" in human_result.output
        assert "kin-blocked [blocked] Needs a decision" in human_result.output

        data = json.loads(json_result.output)
        assert data["tickets"]["blocked"] == 1
        assert data["unassigned"] == ["kin-blocked"]


def test_status_ready_count_uses_global_dependency_state() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        done_branch = ensure_branch_layout(base, "done-feature")
        write_json(done_branch / "state.json", {"status": "done"})
        write_ticket(
            Ticket(id="done-dep", title="Completed elsewhere", status="closed"),
            done_branch / "tickets" / "done-dep.md",
        )
        write_ticket(
            Ticket(id="ready-work", title="Ready work", status="open", deps=["done-dep"]),
            branch_root(base, feature) / "tickets" / "ready-work.md",
        )

        ready_result = runner.invoke(app, ["tk", "list", "--ready"])
        human_result = runner.invoke(app, ["status"])
        json_result = runner.invoke(app, ["status", "--json"])

        assert ready_result.exit_code == 0, ready_result.output
        assert "ready-work" in ready_result.output
        assert human_result.exit_code == 0, human_result.output
        assert "1 ready (1 total)" in human_result.output
        assert json_result.exit_code == 0, json_result.output
        assert json.loads(json_result.output)["ready_count"] == 1


def test_status_ready_count_includes_archived_dependency() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        branch_dir = ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        archived_tickets = archive_root(base) / "finished" / "tickets"
        archived_tickets.mkdir(parents=True)
        write_ticket(
            Ticket(id="archived-dep", title="Completed and archived", status="closed"),
            archived_tickets / "archived-dep.md",
        )
        write_ticket(
            Ticket(id="ready-work", title="Ready work", status="open", deps=["archived-dep"]),
            branch_dir / "tickets" / "ready-work.md",
        )

        ready_result = runner.invoke(app, ["tk", "list", "--ready"])
        human_result = runner.invoke(app, ["status"])
        json_result = runner.invoke(app, ["status", "--json"])

        assert ready_result.exit_code == 0, ready_result.output
        assert "ready-work" in ready_result.output
        assert human_result.exit_code == 0, human_result.output
        assert "1 ready (1 total)" in human_result.output
        assert json_result.exit_code == 0, json_result.output
        assert json.loads(json_result.output)["ready_count"] == 1


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


def test_status_human_assignments_exclude_closed_tickets() -> None:
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
        write_ticket(
            Ticket(id="kin-0003", title="Active work", status="in_progress", assignee="hand"),
            tickets_dir / "kin-0003.md",
        )
        write_ticket(
            Ticket(id="kin-0004", title="Historical work", status="closed", assignee="hand"),
            tickets_dir / "kin-0004.md",
        )

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Assignments:" in result.output
        assert "hand: kin-0001 [open] Assigned" in result.output
        assert "hand: kin-0003 [in_progress] Active work" in result.output
        assert "hand: kin-0002" not in result.output
        assert "kin-0004" not in result.output


def test_status_json_assignments_exclude_closed_tickets() -> None:
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
        write_ticket(
            Ticket(id="kin-0003", title="Historical hand work", status="closed", assignee="hand"),
            tickets_dir / "kin-0003.md",
        )
        write_ticket(
            Ticket(id="kin-0004", title="Historical peasant work", status="closed", assignee="peasant-kin-0002"),
            tickets_dir / "kin-0004.md",
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


def test_status_human_readable_shows_concurrent_context_assignments() -> None:
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
        assert "Contexts (concurrent agent sessions):" in result.output
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


def test_status_check_fails_for_nonterminal_tickets_without_mutating_state() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        branch_dir = ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        write_json(branch_dir / "state.json", {"branch": feature, "custom": "preserved"})
        write_ticket(
            Ticket(id="open-work", title="Open work", status="open"),
            branch_dir / "tickets" / "open-work.md",
        )
        state_before = (branch_dir / "state.json").read_bytes()
        current_before = (base / ".kd" / "current").read_bytes()

        result = runner.invoke(app, ["status", "--check"])

        assert result.exit_code == 1
        assert "Readiness: not ready" in result.output
        assert "open-work [open] Open work" in result.output
        assert (branch_dir / "state.json").read_bytes() == state_before
        assert (base / ".kd" / "current").read_bytes() == current_before


def test_status_check_rejects_invalid_terminal_evidence() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        branch_dir = ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        write_ticket(
            Ticket(id="no-reason", title="Missing evidence", status="closed", resolution="wont-do"),
            branch_dir / "tickets" / "no-reason.md",
        )

        result = runner.invoke(app, ["status", "--check"])

        assert result.exit_code == 1
        assert "Readiness: not ready" in result.output
        assert "no-reason: resolution wont-do requires close_reason" in result.output
        assert "Fix the ticket closure metadata, or reopen and close the ticket again." in result.output


def test_status_json_check_reports_same_readiness_and_failure_details() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        branch_dir = ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        write_ticket(
            Ticket(id="active", title="Active work", status="in_progress"),
            branch_dir / "tickets" / "active.md",
        )
        write_ticket(
            Ticket(id="bad", title="Bad closure", status="closed", resolution="duplicate"),
            branch_dir / "tickets" / "bad.md",
        )

        human_result = runner.invoke(app, ["status", "--check"])
        json_result = runner.invoke(app, ["status", "--check", "--json"])

        assert human_result.exit_code == json_result.exit_code == 1
        assert "Readiness: not ready" in human_result.output
        readiness = json.loads(json_result.output)["readiness"]
        assert readiness["ready"] is False
        assert readiness["nonterminal_tickets"] == [{"id": "active", "status": "in_progress", "title": "Active work"}]
        assert readiness["invalid_terminal_evidence"] == [
            {
                "id": "bad",
                "title": "Bad closure",
                "errors": [
                    "resolution duplicate requires close_reason",
                    "resolution duplicate requires duplicate-of",
                ],
            }
        ]


def test_status_check_reads_legacy_done_workspace_without_mutating_it() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "legacy-feature"
        branch_dir = ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        legacy_state = {"branch": feature, "status": "done", "done_at": "2026-01-01T00:00:00+00:00"}
        write_json(branch_dir / "state.json", legacy_state)
        write_terminal_tickets(
            branch_dir / "tickets",
            [
                Ticket(id="legacy", title="Legacy completion", status="closed"),
                Ticket(
                    id="legacy-dupe",
                    title="Legacy duplicate",
                    status="closed",
                    duplicate_of="legacy",
                ),
                Ticket(
                    id="legacy-old",
                    title="Legacy superseded",
                    status="closed",
                    superseded_by="legacy",
                ),
            ],
        )
        state_before = (branch_dir / "state.json").read_bytes()

        result = runner.invoke(app, ["status", "--check", "--json"])

        assert result.exit_code == 0, result.output
        readiness = json.loads(result.output)["readiness"]
        assert readiness["ready"] is True
        assert readiness["resolutions"]["completed"] == 1
        assert readiness["resolutions"]["duplicate"] == 1
        assert readiness["resolutions"]["superseded"] == 1
        assert readiness["outcomes"]["duplicate"][0]["reason"] == "Duplicate of legacy"
        assert readiness["outcomes"]["superseded"][0]["reason"] == "Superseded by legacy"
        assert (branch_dir / "state.json").read_bytes() == state_before


def test_status_check_succeeds_for_active_workspace_with_valid_terminal_tickets() -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "active-feature"
        branch_dir = ensure_branch_layout(base, feature)
        set_current_run(base, feature)
        write_terminal_tickets(branch_dir / "tickets", terminal_ticket_set())

        human_result = runner.invoke(app, ["status", "--check"])
        json_result = runner.invoke(app, ["status", "--check", "--json"])

        assert human_result.exit_code == json_result.exit_code == 0
        assert "Readiness: ready" in human_result.output
        readiness = json.loads(json_result.output)["readiness"]
        assert readiness["ready"] is True
        assert readiness["resolutions"] == {
            "completed": 1,
            "wont-do": 1,
            "duplicate": 1,
            "superseded": 1,
            "invalid": 1,
        }


@pytest.mark.parametrize(
    ("ticket", "message"),
    [
        (
            Ticket(id="nope", status="closed", title="No reason", resolution="wont-do"),
            "requires close_reason",
        ),
        (
            Ticket(
                id="dupe",
                status="closed",
                title="No reference",
                resolution="duplicate",
                close_reason="Same work",
            ),
            "requires duplicate-of",
        ),
        (
            Ticket(
                id="old",
                status="closed",
                title="No reference",
                resolution="superseded",
                close_reason="Replaced",
            ),
            "requires superseded-by",
        ),
        (
            Ticket(id="bad", status="closed", title="No reason", resolution="invalid"),
            "requires close_reason",
        ),
        (
            Ticket(
                id="odd",
                status="closed",
                title="Unknown outcome",
                resolution="abandoned",
                close_reason="Unknown",
            ),
            "unknown resolution",
        ),
        (
            Ticket(
                id="mixed",
                status="closed",
                title="Mismatched evidence",
                resolution="completed",
                duplicate_of="done",
            ),
            "cannot use duplicate-of or superseded-by",
        ),
    ],
)
def test_status_check_rejects_each_invalid_terminal_evidence_case(ticket: Ticket, message: str) -> None:
    with runner.isolated_filesystem():
        base = Path.cwd()
        branch_dir = ensure_branch_layout(base, "example-feature")
        set_current_run(base, "example-feature")
        write_ticket(ticket, branch_dir / "tickets" / f"{ticket.id}.md")

        result = runner.invoke(app, ["status", "--check"])

        assert result.exit_code == 1
        assert ticket.id in result.output
        assert message in result.output


def test_done_is_not_a_public_command() -> None:
    help_result = runner.invoke(app, ["--help"])
    done_result = runner.invoke(app, ["done"])

    assert help_result.exit_code == 0
    assert "done" not in help_result.output.split("Commands:", maxsplit=1)[-1]
    assert done_result.exit_code == 2
    assert "No such command 'done'" in done_result.output
