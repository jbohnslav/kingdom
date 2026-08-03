"""Release contract for Kingdom's supported coding-agent hosts."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.hook import (
    handle_post_compact,
    handle_post_tool_use,
    handle_pre_compact,
    handle_stop,
    handle_subagent_start,
    handle_subagent_stop,
    handle_user_prompt_submit,
)
from kingdom.cli.plugin import SUPPORTED_HOOK_EVENTS
from kingdom.cli.ticket import ticket_app
from kingdom.codex_plugin import CODEX_HOOK_EVENTS
from kingdom.lifecycle import CURSOR_EVENTS, Host, normalize_host_event
from kingdom.state import (
    branch_root,
    ensure_branch_layout,
    read_execution_ticket_context,
    record_execution_ticket_context,
    resolve_execution_context,
    set_current_run,
)
from kingdom.ticket import Ticket, read_ticket, write_ticket

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST_EVENTS = REPO_ROOT / "tests" / "fixtures" / "host_events.json"
SUPPORT_MATRIX = REPO_ROOT / "docs" / "support-matrix.md"
README = REPO_ROOT / "README.md"
PUBLISH_CHECKLIST = REPO_ROOT / "docs" / "publish-checklist.md"

EXPECTED_EVENT_NAMES = {
    "claude": {
        "SessionStart",
        "SessionEnd",
        "PreCompact",
        "PostCompact",
        "SubagentStart",
        "SubagentStop",
        "UserPromptSubmit",
        "PostToolUse",
        "Stop",
    },
    "codex": {
        "SessionStart",
        "SessionEnd",
        "PreCompact",
        "PostCompact",
        "SubagentStart",
        "SubagentStop",
        "UserPromptSubmit",
        "PostToolUse",
        "Stop",
    },
    "cursor": {
        "sessionStart",
        "sessionEnd",
        "preCompact",
        "subagentStart",
        "subagentStop",
        "beforeSubmitPrompt",
        "postToolUse",
        "stop",
    },
}


def setup_bound_host_ticket(base: Path, host: Host, ticket_id: str = "host1") -> tuple[Path, str]:
    branch = "feature/host-matrix"
    branch_dir = ensure_branch_layout(base, branch)
    set_current_run(base, branch)
    context = resolve_execution_context(host=host.value, session_id=f"{host.value}-session", cwd=base)
    assert context is not None
    ticket_path = branch_dir / "tickets" / f"{ticket_id}.md"
    write_ticket(
        Ticket(
            id=ticket_id,
            status="in_progress",
            title=f"{host.value.title()} host work",
            assignee=context.context_id,
            created=datetime.now(UTC),
        ),
        ticket_path,
    )
    record_execution_ticket_context(base, context, ticket_id, feature=branch)
    return ticket_path, context.context_id


def full_host_event(host: Host, base: Path, event_name: str, **extra: object):
    event = normalize_host_event(
        host,
        {
            "hook_event_name": event_name,
            "session_id": f"{host.value}-session",
            "cwd": str(base),
            **extra,
        },
    )
    assert event is not None
    return event


def test_fixture_events_match_host_contracts() -> None:
    fixtures = json.loads(HOST_EVENTS.read_text(encoding="utf-8"))
    fixture_event_names = {
        host: {case["payload"]["hook_event_name"] for case in cases} for host, cases in fixtures.items()
    }

    assert fixture_event_names == EXPECTED_EVENT_NAMES
    assert fixture_event_names["claude"] == set(SUPPORTED_HOOK_EVENTS)
    assert fixture_event_names["codex"] == set(CODEX_HOOK_EVENTS)
    assert fixture_event_names["cursor"] == set(CURSOR_EVENTS)
    assert "postCompact" not in fixture_event_names["cursor"]


def test_same_branch_claude_codex_and_cursor_bindings_are_isolated() -> None:
    runner = CliRunner()
    host_tickets = {
        "claude": "cla1",
        "codex": "cod1",
        "cursor": "cur1",
    }

    with runner.isolated_filesystem():
        base = Path.cwd()
        branch = "feature/host-matrix"
        ensure_branch_layout(base, branch)
        set_current_run(base, branch)
        tickets_dir = branch_root(base, branch) / "tickets"

        for host, ticket_id in host_tickets.items():
            write_ticket(
                Ticket(
                    id=ticket_id,
                    status="open",
                    title=f"{host.title()} host work",
                    created=datetime.now(UTC),
                ),
                tickets_dir / f"{ticket_id}.md",
            )
            environment = {"KD_CONTEXT": f"{host}-session", "KD_HOST": host}
            with patch.dict(os.environ, environment, clear=True):
                started = runner.invoke(ticket_app, ["start", ticket_id])
            assert started.exit_code == 0, started.output

        for host, ticket_id in host_tickets.items():
            environment = {"KD_CONTEXT": f"{host}-session", "KD_HOST": host}
            with patch.dict(os.environ, environment, clear=True):
                current = runner.invoke(ticket_app, ["current", "--id"])
            assert current.exit_code == 0, current.output
            assert current.output.strip() == ticket_id

        status = runner.invoke(app, ["status", "--json"])
        assert status.exit_code == 0, status.output
        contexts = json.loads(status.output)["contexts"]
        tickets_by_host = {
            context["host"]: context["ticket_id"] for context in contexts if context["ticket_id"] is not None
        }
        assert tickets_by_host == host_tickets


@pytest.mark.parametrize("host", (Host.CLAUDE, Host.CODEX))
def test_full_host_stop_and_compaction_target_exact_binding(host: Host, tmp_path: Path) -> None:
    setup_bound_host_ticket(tmp_path, host)
    handle_user_prompt_submit(full_host_event(host, tmp_path, "UserPromptSubmit"))
    handle_post_tool_use(full_host_event(host, tmp_path, "PostToolUse", tool_name="Edit", tool_input={}))

    stop = json.loads(handle_stop(full_host_event(host, tmp_path, "Stop")))
    pre_compact = json.loads(handle_pre_compact(full_host_event(host, tmp_path, "PreCompact")))
    post_compact = json.loads(handle_post_compact(full_host_event(host, tmp_path, "PostCompact")))

    assert stop["decision"] == "block"
    assert "kd tk log host1" in stop["reason"]
    assert "exact ticket host1" in pre_compact["systemMessage"]
    assert "exact ticket host1" in post_compact["systemMessage"]


@pytest.mark.parametrize("host", (Host.CLAUDE, Host.CODEX))
def test_full_host_subagent_inherits_and_records_handoff(host: Host, tmp_path: Path) -> None:
    ticket_path, parent_context_id = setup_bound_host_ticket(tmp_path, host)
    start = full_host_event(
        host,
        tmp_path,
        "SubagentStart",
        agent_id=f"{host.value}-child",
        agent_type="worker",
    )
    stop = full_host_event(
        host,
        tmp_path,
        "SubagentStop",
        agent_id=f"{host.value}-child",
        agent_type="worker",
    )

    handle_subagent_start(start)
    child = resolve_execution_context(
        host=host.value,
        session_id=f"{host.value}-child",
        role="subagent",
        parent_agent_id=parent_context_id,
        agent_type="worker",
        cwd=tmp_path,
    )
    assert child is not None
    assert read_execution_ticket_context(tmp_path, child)["ticket_id"] == "host1"

    handle_subagent_stop(stop)

    ticket = read_ticket(ticket_path)
    assert ticket.assignee == parent_context_id
    assert "Native subagent worker completed" in ticket.body


def test_published_matrix_has_dated_versioned_host_contract() -> None:
    matrix = SUPPORT_MATRIX.read_text(encoding="utf-8")

    for required_text in (
        "Verified: 2026-08-03",
        "Kingdom: 1.0.0",
        "Baseline commit: `676d4894f7a8c931ee3ff7b8673d36d54d84bd35`",
        "Claude Code 2.1.220",
        "Codex CLI 0.146.0-alpha.9.2",
        "Cursor Agent 2026.02.27-e7d2ef6",
        "Cursor desktop 3.14.7",
        "**Live**",
        "**Contract**",
        "**Limited**",
        "**Unsupported**",
        "same branch",
        "stale state",
        "fails open",
        "missing-host failure",
        "| Host | Install and update | Session isolation and Stop | Compaction | Native subagents | Uninstall |",
        "`kd plugin disable`",
        "`kd plugin uninstall codex`",
        "Cursor has no `postCompact`",
        "`subagentStop` omits the child ID",
        "https://cursor.com/docs/hooks",
        "https://cursor.com/changelog/side-chat",
    ):
        assert required_text in matrix

    readme = README.read_text(encoding="utf-8")
    checklist = PUBLISH_CHECKLIST.read_text(encoding="utf-8")
    assert "[supported host integration matrix](docs/support-matrix.md)" in readme
    assert "[supported host integration matrix](support-matrix.md)" in checklist
    for command in (
        "claude --version",
        "codex --version",
        "cursor-agent --version",
        "cursor --version",
        "uv run pytest tests/test_host_integration_matrix.py",
    ):
        assert command in checklist
