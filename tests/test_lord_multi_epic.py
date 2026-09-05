"""Integration coverage for concurrent lords on one feature branch."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import typer

from kingdom.cli.peasant import peasant_accept, resolve_peasant_context, start_peasant
from kingdom.lord_harness import get_children_summary, get_startable_children, run_lord_loop
from kingdom.session import get_agent_state, update_agent_state
from kingdom.state import branch_root, read_json, write_json
from kingdom.ticket import Ticket, read_ticket, write_ticket
from kingdom.worktree import create_worktree, design_state_path

BRANCH = "feature/multi-epic"


def write_epic(base: Path, ticket_id: str) -> Path:
    path = branch_root(base, BRANCH) / "tickets" / f"{ticket_id}.md"
    write_ticket(
        Ticket(
            id=ticket_id,
            status="in_progress",
            title=f"Epic {ticket_id}",
            type="epic",
            created=datetime.now(UTC),
        ),
        path,
    )
    return path


def write_child(
    base: Path,
    ticket_id: str,
    parent: str,
    *,
    status: str = "open",
    deps: list[str] | None = None,
) -> Path:
    path = branch_root(base, BRANCH) / "tickets" / f"{ticket_id}.md"
    write_ticket(
        Ticket(
            id=ticket_id,
            status=status,
            title=f"Child {ticket_id}",
            parent=parent,
            deps=deps or [],
            created=datetime.now(UTC),
        ),
        path,
    )
    return path


def set_ticket_status(path: Path, status: str) -> None:
    ticket = read_ticket(path)
    ticket.status = status
    write_ticket(ticket, path)


@pytest.fixture
def multi_epic_project(project_with_run: Path) -> Path:
    write_epic(project_with_run, "epic-a")
    write_epic(project_with_run, "epic-b")
    write_child(project_with_run, "a1", "epic-a", status="closed")
    write_child(project_with_run, "a2", "epic-a")
    write_child(project_with_run, "b1", "epic-b", deps=["a2"])
    write_child(project_with_run, "b2", "epic-b")
    write_child(project_with_run, "b-epic", "epic-b", deps=["epic-a"])
    update_agent_state(project_with_run, BRANCH, "lord-epic-a", status="working", ticket="epic-a")
    update_agent_state(project_with_run, BRANCH, "lord-epic-b", status="working", ticket="epic-b")
    return project_with_run


def startable_ids(base: Path, epic_id: str) -> set[str]:
    return {ticket_id for _, ticket_id in get_startable_children(base, BRANCH, epic_id)}


def test_cross_epic_leaf_close_wakes_only_the_blocked_lord(multi_epic_project: Path) -> None:
    epic_a_startable = startable_ids(multi_epic_project, "epic-a")
    epic_b_startable = startable_ids(multi_epic_project, "epic-b")
    before = get_children_summary(multi_epic_project, BRANCH, "epic-b")

    assert epic_a_startable == {"a2"}
    assert epic_b_startable == {"b2"}
    assert epic_a_startable.isdisjoint(epic_b_startable)

    set_ticket_status(branch_root(multi_epic_project, BRANCH) / "tickets" / "a2.md", "closed")
    after = get_children_summary(multi_epic_project, BRANCH, "epic-b")

    assert after != before
    assert startable_ids(multi_epic_project, "epic-b") == {"b1", "b2"}
    assert read_ticket(branch_root(multi_epic_project, BRANCH) / "tickets" / "epic-a.md").status == "in_progress"

    set_ticket_status(branch_root(multi_epic_project, BRANCH) / "tickets" / "epic-a.md", "closed")
    assert startable_ids(multi_epic_project, "epic-b") == {"b-epic", "b1", "b2"}


def test_peasant_start_rejects_cross_epic_block_and_duplicate_launch(multi_epic_project: Path) -> None:
    blocked = resolve_peasant_context("b1", base=multi_epic_project, auto_pull=True)
    with pytest.raises(typer.Exit):
        start_peasant(blocked, agent="claude", hand=False, tmux=False, no_preflight=True)

    assert read_ticket(blocked.ticket_path).status == "open"

    startable = resolve_peasant_context("b2", base=multi_epic_project, auto_pull=True)
    both_started = Barrier(2)
    second_invocation_started = Event()
    release_launch = Event()

    def launch_once(*args, **kwargs):
        assert release_launch.wait(timeout=3)
        return 4242

    def invoke_start(invocation: int) -> str:
        both_started.wait(timeout=2)
        if invocation == 2:
            second_invocation_started.set()
        try:
            start_peasant(startable, agent="claude", hand=False, tmux=False, no_preflight=True)
        except typer.Exit:
            return "rejected"
        return "started"

    with (
        patch("kingdom.cli.peasant.create_worktree", return_value=multi_epic_project / "b2-worktree"),
        patch("kingdom.cli.launch_work_background", side_effect=launch_once) as launch,
        patch("kingdom.cli.peasant.is_process_alive", return_value=True),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(invoke_start, 1)
        second = executor.submit(invoke_start, 2)
        assert second_invocation_started.wait(timeout=2)
        release_launch.set()
        outcomes = {first.result(timeout=3), second.result(timeout=3)}

    assert outcomes == {"started", "rejected"}
    assert launch.call_count == 1


def test_stopping_and_restarting_one_lord_does_not_stop_the_other(multi_epic_project: Path) -> None:
    epic_b_running = Event()
    release_epic_b = Event()
    epic_a_calls = 0
    epic_a_calls_lock = Lock()

    def build_scripted_command(agent_config, prompt, resume_id, *, streaming):
        epic_id = "epic-a" if "**Epic ID:** epic-a" in prompt else "epic-b"
        return [epic_id]

    def run_scripted_lord(command, **kwargs):
        nonlocal epic_a_calls
        if command == ["epic-a"]:
            with epic_a_calls_lock:
                epic_a_calls += 1
                call_number = epic_a_calls
            if call_number == 1:
                update_agent_state(multi_epic_project, BRANCH, "lord-epic-a", status="stopping")
                return SimpleNamespace(stdout="STATUS: CONTINUE", stderr="", returncode=0)
            return SimpleNamespace(stdout="STATUS: DONE", stderr="", returncode=0)
        epic_b_running.set()
        assert release_epic_b.wait(timeout=3)
        return SimpleNamespace(stdout="STATUS: DONE", stderr="", returncode=0)

    def parse_scripted_response(agent_config, stdout, stderr, returncode):
        return stdout, None, stdout

    with (
        patch("kingdom.lord_harness.signal.signal"),
        patch("kingdom.lord_harness.time.sleep"),
        patch("kingdom.lord_harness.build_command", side_effect=build_scripted_command),
        patch("kingdom.lord_harness.run_lord_streaming_subprocess", side_effect=run_scripted_lord),
        patch("kingdom.lord_harness.parse_response", side_effect=parse_scripted_response),
        ThreadPoolExecutor(max_workers=3) as executor,
    ):
        epic_a = executor.submit(
            run_lord_loop,
            multi_epic_project,
            BRANCH,
            "claude",
            "epic-a",
            "lord-epic-a",
            3,
            5,
        )
        epic_b = executor.submit(
            run_lord_loop,
            multi_epic_project,
            BRANCH,
            "claude",
            "epic-b",
            "lord-epic-b",
            3,
            5,
        )
        assert epic_a.result(timeout=3) == "stopped"
        assert epic_b_running.wait(timeout=2)
        assert not epic_b.done()
        assert get_agent_state(multi_epic_project, BRANCH, "lord-epic-b").status == "working"

        update_agent_state(multi_epic_project, BRANCH, "lord-epic-a", status="working")
        restarted = executor.submit(
            run_lord_loop,
            multi_epic_project,
            BRANCH,
            "claude",
            "epic-a",
            "lord-epic-a",
            2,
            3,
        )
        assert restarted.result(timeout=3) == "done"
        assert not epic_b.done()
        release_epic_b.set()
        assert epic_b.result(timeout=3) == "done"

    assert get_agent_state(multi_epic_project, BRANCH, "lord-epic-a").status == "done"
    assert get_agent_state(multi_epic_project, BRANCH, "lord-epic-b").status == "done"
    assert read_ticket(branch_root(multi_epic_project, BRANCH) / "tickets" / "epic-b.md").status == "in_progress"
    assert read_ticket(branch_root(multi_epic_project, BRANCH) / "tickets" / "epic-a.md").status == "in_progress"


def test_concurrent_worktree_bookkeeping_and_accepts_are_serialized(
    multi_epic_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_barrier = Barrier(2)

    def run_worktree_git(command, **kwargs):
        if command == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, f"{BRANCH}\n", "")
        if command[:3] == ["git", "rev-parse", "--verify"]:
            return subprocess.CompletedProcess(command, 1, "", "")
        if command[:3] == ["git", "worktree", "add"]:
            Path(command[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(command)

    def delayed_write(path: Path, state: dict) -> None:
        # Align the legacy read-then-write path so its lost update is deterministic.
        # The locked implementation bypasses this patched module attribute.
        write_barrier.wait(timeout=2)
        write_json(path, state)

    with (
        patch("kingdom.worktree.subprocess.run", side_effect=run_worktree_git),
        patch("kingdom.worktree.run_init_script"),
        patch("kingdom.worktree.write_json", create=True, side_effect=delayed_write),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        created = [
            executor.submit(create_worktree, multi_epic_project, ticket_id, git_root=multi_epic_project)
            for ticket_id in ("a2", "b2")
        ]
        for future in created:
            future.result(timeout=3)

    state_path = design_state_path(multi_epic_project, BRANCH)
    assert set(read_json(state_path)["worktrees"]) == {"a2", "b2"}

    tickets = branch_root(multi_epic_project, BRANCH) / "tickets"
    for ticket_id in ("a2", "b2"):
        set_ticket_status(tickets / f"{ticket_id}.md", "in_review")
        update_agent_state(
            multi_epic_project,
            BRANCH,
            f"peasant-{ticket_id}",
            status="needs_king_review",
            ticket=ticket_id,
        )

    monkeypatch.setenv("KD_BASE", str(multi_epic_project))
    first_merge_started = Event()
    release_first_merge = Event()
    second_merge_started = Event()
    second_accept_reached_lock = Event()
    merge_counter = 0
    merge_counter_lock = Lock()

    def run_accept_git(command, **kwargs):
        nonlocal merge_counter
        if command == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, f"{BRANCH}\n", "")
        if command[:3] == ["git", "merge-base", "--is-ancestor"]:
            return subprocess.CompletedProcess(command, 1, "", "")
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["git", "merge"]:
            with merge_counter_lock:
                merge_counter += 1
                merge_number = merge_counter
            if merge_number == 1:
                first_merge_started.set()
                assert release_first_merge.wait(timeout=3)
            else:
                second_merge_started.set()
            return subprocess.CompletedProcess(command, 0, "merged", "")
        raise AssertionError(command)

    from kingdom.state import flock as real_flock

    lock_calls = 0
    lock_calls_guard = Lock()

    def observed_flock(lock_path, **kwargs):
        nonlocal lock_calls
        with lock_calls_guard:
            lock_calls += 1
            call_number = lock_calls
        if call_number == 2:
            second_accept_reached_lock.set()
        return real_flock(lock_path, **kwargs)

    with (
        patch("kingdom.cli.peasant.resolve_invocation_git_root", return_value=multi_epic_project),
        patch("kingdom.cli.peasant.subprocess.run", side_effect=run_accept_git),
        patch("kingdom.cli.peasant.cleanup_accepted_peasant"),
        patch("kingdom.cli.peasant.flock", side_effect=observed_flock),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first = executor.submit(peasant_accept, "a2")
        assert first_merge_started.wait(timeout=2)
        second = executor.submit(peasant_accept, "b2")
        assert second_accept_reached_lock.wait(timeout=2)
        overlapped = second_merge_started.wait(timeout=0.5)
        release_first_merge.set()
        first.result(timeout=3)
        second.result(timeout=3)

    assert overlapped is False
    assert read_ticket(tickets / "a2.md").status == "closed"
    assert read_ticket(tickets / "b2.md").status == "closed"
    assert get_agent_state(multi_epic_project, BRANCH, "peasant-a2").status == "done"
    assert get_agent_state(multi_epic_project, BRANCH, "peasant-b2").status == "done"


def test_accept_lock_timeout_fails_without_mutating_ticket(
    multi_epic_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KD_BASE", str(multi_epic_project))
    ticket_path = branch_root(multi_epic_project, BRANCH) / "tickets" / "b2.md"

    with (
        patch("kingdom.cli.peasant.flock", side_effect=TimeoutError),
        pytest.raises(typer.Exit) as exc_info,
    ):
        peasant_accept("b2")

    assert exc_info.value.exit_code == 1
    assert read_ticket(ticket_path).status == "open"
