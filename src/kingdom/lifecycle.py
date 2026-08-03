"""Small, content-free lifecycle model shared by host hook adapters."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Host(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR = "cursor"


class EventKind(StrEnum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    PROMPT_SUBMIT = "prompt_submit"
    POST_TOOL_USE = "post_tool_use"
    STOP = "stop"


class InvalidHostEvent(ValueError):
    """A known host event is missing provenance Kingdom requires."""


@dataclass(frozen=True)
class HostEvent:
    host: Host
    kind: EventKind
    session_id: str
    cwd: Path
    agent_id: str | None = None
    parent_agent_id: str | None = None
    agent_type: str | None = None
    ticket_hint: str | None = None
    source: str | None = None
    trigger: str | None = None
    reason: str | None = None
    tool_name: str | None = None
    file_paths: tuple[str, ...] = ()
    command: str | None = None
    stop_hook_active: bool = False


COMMON_EVENTS = {
    "SessionStart": EventKind.SESSION_START,
    "SessionEnd": EventKind.SESSION_END,
    "PreCompact": EventKind.PRE_COMPACT,
    "PostCompact": EventKind.POST_COMPACT,
    "SubagentStart": EventKind.SUBAGENT_START,
    "SubagentStop": EventKind.SUBAGENT_STOP,
    "UserPromptSubmit": EventKind.PROMPT_SUBMIT,
    "PostToolUse": EventKind.POST_TOOL_USE,
    "Stop": EventKind.STOP,
}

CURSOR_EVENTS = {
    "sessionStart": EventKind.SESSION_START,
    "sessionEnd": EventKind.SESSION_END,
    "preCompact": EventKind.PRE_COMPACT,
    "subagentStart": EventKind.SUBAGENT_START,
    "subagentStop": EventKind.SUBAGENT_STOP,
    "beforeSubmitPrompt": EventKind.PROMPT_SUBMIT,
    "postToolUse": EventKind.POST_TOOL_USE,
    "stop": EventKind.STOP,
}

PATCH_FILE_PATTERN = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)


def optional_string(payload: Mapping[str, object], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def required_string(payload: Mapping[str, object], label: str, *names: str) -> str:
    value = optional_string(payload, *names)
    if value is None:
        raise InvalidHostEvent(f"missing required {label}")
    if "\n" in value or "\r" in value:
        raise InvalidHostEvent(f"{label} must be a single-line string")
    return value


def event_cwd(host: Host, payload: Mapping[str, object]) -> str | None:
    cwd = optional_string(payload, "cwd")
    if cwd:
        return cwd

    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str) and roots[0]:
        return roots[0]

    if host is Host.CURSOR:
        return os.environ.get("CURSOR_PROJECT_DIR")
    if host is Host.CLAUDE:
        return os.environ.get("CLAUDE_PROJECT_DIR")
    return None


def normalized_file_paths(tool_name: str | None, payload: Mapping[str, object]) -> tuple[str, ...]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return ()

    file_path = optional_string(tool_input, "file_path")
    if file_path:
        return (file_path,)

    if tool_name != "apply_patch":
        return ()
    patch = optional_string(tool_input, "command")
    return tuple(PATCH_FILE_PATTERN.findall(patch or ""))


def normalized_command(tool_name: str | None, payload: Mapping[str, object]) -> str | None:
    if tool_name not in {"Bash", "Shell"}:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return None
    return optional_string(tool_input, "command")


def normalize_host_event(host: Host, payload: Mapping[str, object]) -> HostEvent | None:
    event_name = required_string(payload, "hook_event_name", "hook_event_name")
    event_names = CURSOR_EVENTS if host is Host.CURSOR else COMMON_EVENTS
    kind = event_names.get(event_name)
    if kind is None:
        return None

    session_names = ("session_id", "conversation_id") if host is Host.CURSOR else ("session_id",)
    session_id = required_string(payload, "session_id", *session_names)
    cwd = event_cwd(host, payload)
    if cwd is None:
        raise InvalidHostEvent("missing required cwd")

    tool_name = optional_string(payload, "tool_name")
    return HostEvent(
        host=host,
        kind=kind,
        session_id=session_id,
        cwd=Path(cwd),
        agent_id=optional_string(payload, "agent_id", "subagent_id"),
        parent_agent_id=optional_string(payload, "parent_agent_id", "parent_subagent_id"),
        agent_type=optional_string(payload, "agent_type", "subagent_type"),
        ticket_hint=optional_string(payload, "ticket_hint", "ticket_id"),
        source=optional_string(payload, "source"),
        trigger=optional_string(payload, "trigger"),
        reason=optional_string(payload, "reason"),
        tool_name=tool_name,
        file_paths=normalized_file_paths(tool_name, payload),
        command=normalized_command(tool_name, payload),
        stop_hook_active=payload.get("stop_hook_active") is True,
    )
