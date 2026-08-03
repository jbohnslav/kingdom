"""Normalization tests for documented host lifecycle payloads."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.lifecycle import EventKind, Host, InvalidHostEvent, normalize_host_event

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "host_events.json"


def documented_events() -> dict[str, list[dict[str, object]]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("host", "case"),
    [(host, case) for host, cases in documented_events().items() for case in cases],
)
def test_documented_payloads_normalize(host: str, case: dict[str, object]) -> None:
    event = normalize_host_event(Host(host), case["payload"])

    assert event is not None
    assert event.host is Host(host)
    assert event.kind is EventKind(case["expected"])
    assert event.session_id
    assert event.cwd == Path("/workspace")


def test_event_model_covers_required_lifecycle() -> None:
    assert {
        EventKind.SESSION_START,
        EventKind.SESSION_END,
        EventKind.PRE_COMPACT,
        EventKind.POST_COMPACT,
        EventKind.SUBAGENT_START,
        EventKind.SUBAGENT_STOP,
        EventKind.PROMPT_SUBMIT,
        EventKind.STOP,
    } <= set(EventKind)


def test_sensitive_and_unknown_fields_are_discarded() -> None:
    event = normalize_host_event(
        Host.CODEX,
        {
            "hook_event_name": "SubagentStop",
            "session_id": "thread-1",
            "cwd": "/workspace",
            "agent_id": "agent-1",
            "agent_type": "worker",
            "prompt": "secret prompt",
            "last_assistant_message": "secret response",
            "transcript_path": "/secret/transcript.jsonl",
            "vendor_future_field": "secret future value",
        },
    )

    serialized = json.dumps(asdict(event), default=str)
    assert "secret" not in serialized
    assert event.agent_id == "agent-1"
    assert event.agent_type == "worker"


def test_parent_agent_and_ticket_hint_are_normalized() -> None:
    event = normalize_host_event(
        Host.CLAUDE,
        {
            "hook_event_name": "SubagentStart",
            "session_id": "session-1",
            "cwd": "/workspace",
            "agent_id": "child-1",
            "parent_agent_id": "parent-1",
            "ticket_hint": "abcd",
        },
    )

    assert event is not None
    assert event.agent_id == "child-1"
    assert event.parent_agent_id == "parent-1"
    assert event.ticket_hint == "abcd"


@pytest.mark.parametrize("missing", ["session_id", "cwd"])
def test_missing_required_field_fails_loudly(missing: str) -> None:
    payload = {
        "hook_event_name": "SessionStart",
        "session_id": "session-1",
        "cwd": "/workspace",
    }
    payload.pop(missing)

    with pytest.raises(InvalidHostEvent, match=missing):
        normalize_host_event(Host.CODEX, payload)


def test_unknown_event_is_ignored() -> None:
    assert (
        normalize_host_event(
            Host.CLAUDE,
            {
                "hook_event_name": "FutureVendorEvent",
                "session_id": "session-1",
                "cwd": "/workspace",
            },
        )
        is None
    )


def test_hook_cli_reports_diagnostic_but_fails_open() -> None:
    result = runner.invoke(
        app,
        ["hook", "run", "--host", "codex"],
        input='{"hook_event_name":"SessionStart","cwd":"/workspace"}',
    )

    assert result.exit_code == 0
    assert "session_id" in result.output
