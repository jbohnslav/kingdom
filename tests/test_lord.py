"""Tests for lord agent — epic-scoped supervisor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli.lord import lord_app
from kingdom.lord_harness import (
    all_children_closed,
    build_lord_prompt,
    discover_epic_children,
    extract_lord_summary,
    get_completed_peasants,
    get_startable_children,
    lord_session_name,
    parse_lord_status,
)
from kingdom.session import get_agent_state, update_agent_state
from kingdom.state import branch_root, ensure_branch_layout, set_current_run
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()

BRANCH = "feature/lord-test"


def setup_project(base: Path) -> None:
    ensure_branch_layout(base, BRANCH)
    set_current_run(base, BRANCH)


def tickets_dir(base: Path) -> Path:
    return branch_root(base, BRANCH) / "tickets"


def make_epic(base: Path, epic_id: str = "epic1", title: str = "Test Epic") -> tuple[Ticket, Path]:
    tdir = tickets_dir(base)
    tdir.mkdir(parents=True, exist_ok=True)
    epic = Ticket(
        id=epic_id,
        status="open",
        title=title,
        type="epic",
        body="Epic body.\n\n## Acceptance Criteria\n\n- [ ] AC1\n- [ ] AC2",
        created=datetime.now(UTC),
    )
    path = tdir / f"{epic_id}.md"
    write_ticket(epic, path)
    return epic, path


def make_child(
    base: Path,
    child_id: str,
    epic_id: str,
    title: str = "Child task",
    status: str = "open",
    deps: list[str] | None = None,
) -> tuple[Ticket, Path]:
    tdir = tickets_dir(base)
    tdir.mkdir(parents=True, exist_ok=True)
    child = Ticket(
        id=child_id,
        status=status,
        title=title,
        type="task",
        body="Child body.",
        parent=epic_id,
        deps=deps or [],
        created=datetime.now(UTC),
    )
    path = tdir / f"{child_id}.md"
    write_ticket(child, path)
    return child, path


class TestLordSessionName:
    def test_format(self) -> None:
        assert lord_session_name("epic1") == "lord-epic1"

    def test_with_prefix(self) -> None:
        assert lord_session_name("abc0") == "lord-abc0"


class TestParseLordStatus:
    def test_done(self) -> None:
        assert parse_lord_status("All done.\nSTATUS: DONE") == ("done", None)

    def test_continue(self) -> None:
        assert parse_lord_status("Working...\nSTATUS: CONTINUE") == ("continue", None)

    def test_blocked(self) -> None:
        assert parse_lord_status("Stuck.\nSTATUS: BLOCKED") == ("blocked", None)

    def test_stopped(self) -> None:
        assert parse_lord_status("Shutting down.\nSTATUS: STOPPED") == ("stopped", None)

    def test_escalate(self) -> None:
        status, ticket = parse_lord_status("Ticket failing.\nSTATUS: ESCALATE abc1")
        assert status == "escalate"
        assert ticket == "abc1"

    def test_case_insensitive(self) -> None:
        assert parse_lord_status("STATUS: done")[0] == "done"

    def test_no_status_defaults_continue(self) -> None:
        assert parse_lord_status("No status line here.") == ("continue", None)


class TestExtractLordSummary:
    def test_extracts_first_paragraph(self) -> None:
        text = "Started 3 peasants.\n\nOther details.\n\nSTATUS: CONTINUE"
        assert extract_lord_summary(text) == "Started 3 peasants."

    def test_skips_headings(self) -> None:
        text = "## Summary\n\nDid stuff.\n\nSTATUS: DONE"
        assert extract_lord_summary(text) == "Did stuff."

    def test_truncates_long(self) -> None:
        text = "A" * 600 + "\n\nSTATUS: DONE"
        summary = extract_lord_summary(text)
        assert len(summary) <= 500
        assert summary.endswith("...")

    def test_empty_response(self) -> None:
        assert extract_lord_summary("STATUS: DONE") == ""


class TestDiscoverEpicChildren:
    def test_finds_children(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")
        make_child(project_with_run, "ch02", "epic1")

        children = discover_epic_children(project_with_run, BRANCH, "epic1")
        assert len(children) == 2
        child_ids = {p.stem for p in children}
        assert child_ids == {"ch01", "ch02"}

    def test_excludes_unrelated(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")
        make_child(project_with_run, "ch99", "other-epic")

        children = discover_epic_children(project_with_run, BRANCH, "epic1")
        assert len(children) == 1

    def test_no_children(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        children = discover_epic_children(project_with_run, BRANCH, "epic1")
        assert children == []


class TestGetStartableChildren:
    def test_open_no_deps(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")
        make_child(project_with_run, "ch02", "epic1")

        startable = get_startable_children(project_with_run, BRANCH, "epic1")
        assert len(startable) == 2

    def test_excludes_closed(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="closed")

        startable = get_startable_children(project_with_run, BRANCH, "epic1")
        assert len(startable) == 0

    def test_excludes_in_progress(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="in_progress")

        startable = get_startable_children(project_with_run, BRANCH, "epic1")
        assert len(startable) == 0

    def test_excludes_blocked_deps(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")
        make_child(project_with_run, "ch02", "epic1", deps=["ch01"])

        startable = get_startable_children(project_with_run, BRANCH, "epic1")
        # Only ch01 is startable (ch02 depends on ch01 which is open)
        assert len(startable) == 1
        assert startable[0][1] == "ch01"

    def test_excludes_active_peasant(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")

        # Simulate a running peasant
        update_agent_state(project_with_run, BRANCH, "peasant-ch01", status="working")

        startable = get_startable_children(project_with_run, BRANCH, "epic1")
        assert len(startable) == 0


class TestGetCompletedPeasants:
    def test_finds_needs_king_review(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="in_review")

        update_agent_state(project_with_run, BRANCH, "peasant-ch01", status="needs_king_review")

        completed = get_completed_peasants(project_with_run, BRANCH, "epic1")
        assert len(completed) == 1
        assert completed[0][0] == "ch01"

    def test_excludes_working(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="in_progress")

        update_agent_state(project_with_run, BRANCH, "peasant-ch01", status="working")

        completed = get_completed_peasants(project_with_run, BRANCH, "epic1")
        assert len(completed) == 0


class TestAllChildrenClosed:
    def test_all_closed(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="closed")
        make_child(project_with_run, "ch02", "epic1", status="closed")

        assert all_children_closed(project_with_run, BRANCH, "epic1") is True

    def test_not_all_closed(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="closed")
        make_child(project_with_run, "ch02", "epic1", status="open")

        assert all_children_closed(project_with_run, BRANCH, "epic1") is False

    def test_no_children_returns_false(self, project_with_run: Path) -> None:
        make_epic(project_with_run)
        assert all_children_closed(project_with_run, BRANCH, "epic1") is False


class TestBuildLordPrompt:
    def test_contains_epic_info(self, project_with_run: Path) -> None:
        _, epic_path = make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")

        prompt = build_lord_prompt(epic_path, "epic1", project_with_run, BRANCH)
        assert "Test Epic" in prompt
        assert "epic1" in prompt
        assert "You are a lord" in prompt

    def test_lists_children(self, project_with_run: Path) -> None:
        _, epic_path = make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", title="First child")
        make_child(project_with_run, "ch02", "epic1", title="Second child")

        prompt = build_lord_prompt(epic_path, "epic1", project_with_run, BRANCH)
        assert "ch01" in prompt
        assert "ch02" in prompt
        assert "First child" in prompt

    def test_shows_startable_section(self, project_with_run: Path) -> None:
        _, epic_path = make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")

        prompt = build_lord_prompt(epic_path, "epic1", project_with_run, BRANCH)
        assert "Startable Tickets" in prompt

    def test_shows_toolkit(self, project_with_run: Path) -> None:
        _, epic_path = make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")

        prompt = build_lord_prompt(epic_path, "epic1", project_with_run, BRANCH)
        assert "kd peasant start" in prompt
        assert "kd peasant status" in prompt
        assert "kd peasant accept" in prompt
        assert "kd peasant reject" in prompt

    def test_stop_signal(self, project_with_run: Path) -> None:
        _, epic_path = make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1")

        prompt = build_lord_prompt(
            epic_path,
            "epic1",
            project_with_run,
            BRANCH,
            stop_requested=True,
        )
        assert "STOP SIGNAL RECEIVED" in prompt

    def test_escalation_warning(self, project_with_run: Path) -> None:
        _, epic_path = make_epic(project_with_run)
        make_child(project_with_run, "ch01", "epic1", status="in_progress")

        update_agent_state(
            project_with_run,
            BRANCH,
            "peasant-ch01",
            status="working",
            review_bounce_count=2,
        )

        prompt = build_lord_prompt(epic_path, "epic1", project_with_run, BRANCH)
        assert "Escalation Warning" in prompt


class TestLordCLIStart:
    def test_start_requires_epic(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        tdir.mkdir(parents=True, exist_ok=True)
        task = Ticket(
            id="tsk1",
            status="open",
            title="Not an epic",
            type="task",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(task, tdir / "tsk1.md")

        result = runner.invoke(lord_app, ["start", "tsk1"])
        assert result.exit_code == 1
        assert "not an epic" in result.output.lower()

    def test_start_rejects_closed_epic(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        tdir.mkdir(parents=True, exist_ok=True)
        epic = Ticket(
            id="epic1",
            status="closed",
            title="Closed epic",
            type="epic",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(epic, tdir / "epic1.md")

        result = runner.invoke(lord_app, ["start", "epic1"])
        assert result.exit_code == 1
        assert "closed" in result.output.lower()

    def test_start_launches_lord(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        tdir.mkdir(parents=True, exist_ok=True)
        epic = Ticket(
            id="epic1",
            status="open",
            title="Test Epic",
            type="epic",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(epic, tdir / "epic1.md")

        with patch("kingdom.cli.lord.launch_lord_background", return_value=99999):
            result = runner.invoke(lord_app, ["start", "epic1"])
        assert result.exit_code == 0, result.output
        assert "lord-epic1" in result.output
        assert "99999" in result.output

        # Verify session was created
        state = get_agent_state(cli_project, BRANCH, "lord-epic1")
        assert state.status == "working"
        assert state.ticket == "epic1"
        assert state.pid == 99999

    def test_start_transitions_epic_to_in_progress(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        tdir.mkdir(parents=True, exist_ok=True)
        epic = Ticket(
            id="epic1",
            status="open",
            title="Test Epic",
            type="epic",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(epic, tdir / "epic1.md")

        with patch("kingdom.cli.lord.launch_lord_background", return_value=99999):
            result = runner.invoke(lord_app, ["start", "epic1"])
        assert result.exit_code == 0

        from kingdom.ticket import read_ticket

        updated = read_ticket(tdir / "epic1.md")
        assert updated.status == "in_progress"

    def test_start_rejects_duplicate(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        tdir.mkdir(parents=True, exist_ok=True)
        epic = Ticket(
            id="epic1",
            status="open",
            title="Test Epic",
            type="epic",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(epic, tdir / "epic1.md")

        # Simulate a running lord
        update_agent_state(cli_project, BRANCH, "lord-epic1", status="working", pid=12345)

        with patch("kingdom.cli.lord.is_process_alive", return_value=True):
            result = runner.invoke(lord_app, ["start", "epic1"])
        assert result.exit_code == 1
        assert "already running" in result.output.lower()


class TestLordCLIStop:
    def test_stop_without_running_lord(self, cli_project: Path) -> None:
        result = runner.invoke(lord_app, ["stop"])
        assert result.exit_code == 1
        assert "no running lord" in result.output.lower()

    def test_stop_with_force(self, cli_project: Path) -> None:
        tdir = tickets_dir(cli_project)
        tdir.mkdir(parents=True, exist_ok=True)
        epic = Ticket(
            id="epic1",
            status="in_progress",
            title="Test Epic",
            type="epic",
            body="",
            created=datetime.now(UTC),
        )
        write_ticket(epic, tdir / "epic1.md")

        update_agent_state(cli_project, BRANCH, "lord-epic1", status="working")

        result = runner.invoke(lord_app, ["stop", "epic1", "--force"])
        assert result.exit_code == 0

        state = get_agent_state(cli_project, BRANCH, "lord-epic1")
        assert state.status == "stopped"


class TestLordCLIStatus:
    def test_status_no_lords(self, cli_project: Path) -> None:
        result = runner.invoke(lord_app, ["status"])
        assert result.exit_code == 0
        assert "no lord agents" in result.output.lower()

    def test_status_json(self, cli_project: Path) -> None:
        update_agent_state(
            cli_project,
            BRANCH,
            "lord-epic1",
            status="working",
            ticket="epic1",
            agent_backend="claude",
        )

        result = runner.invoke(lord_app, ["status", "--json"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["epic_id"] == "epic1"
        assert data[0]["status"] == "working"


class TestLordWorker:
    def test_main_requires_args(self) -> None:
        from kingdom.lord_worker import main

        with pytest.raises(SystemExit):
            main([])
