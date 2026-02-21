"""Agent configuration and command building.

Each agent has a backend (claude_code, codex, cursor) whose CLI invocation
details live in ``BACKEND_DEFAULTS``.  User-facing config (model, prompts,
extra flags) comes from ``config.py``'s ``AgentDef``.  The two are merged at
runtime into an ``AgentConfig`` that command builders consume.
"""

from __future__ import annotations

import json
import logging
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field

from kingdom.config import AgentDef

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend defaults — CLI invocation details that live in code, not config
# ---------------------------------------------------------------------------

BACKEND_DEFAULTS: dict[str, dict[str, str]] = {
    "claude_code": {
        "cli": "claude --print --output-format json",
        "resume_flag": "--resume",
        "version_command": "claude --version",
        "install_hint": "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code",
    },
    "codex": {
        "cli": "codex exec --json",
        "resume_flag": "resume",
        "version_command": "codex --version",
        "install_hint": "Install Codex CLI: npm install -g @openai/codex",
    },
    "cursor": {
        "cli": "agent --print --output-format json",
        "resume_flag": "--resume",
        "version_command": "agent --version",
        "install_hint": "Install Cursor Agent: https://docs.cursor.com/agent",
    },
}


# ---------------------------------------------------------------------------
# Runtime agent config (merges backend defaults + user config)
# ---------------------------------------------------------------------------


@dataclass
class AgentConfig:
    """Runtime agent configuration, merging BACKEND_DEFAULTS with user AgentDef."""

    name: str
    backend: str
    cli: str
    resume_flag: str
    version_command: str = ""
    install_hint: str = ""
    model: str = ""
    extra_flags: list[str] = field(default_factory=list)


def resolve_agent(name: str, agent_def: AgentDef) -> AgentConfig:
    """Merge backend defaults with a user-facing AgentDef into a runtime AgentConfig.

    Raises:
        ValueError: If the backend is not in BACKEND_DEFAULTS.
    """
    defaults = BACKEND_DEFAULTS.get(agent_def.backend)
    if defaults is None:
        raise ValueError(
            f"Unknown backend '{agent_def.backend}' for agent '{name}'. "
            f"Known backends: {', '.join(sorted(BACKEND_DEFAULTS))}"
        )
    return AgentConfig(
        name=name,
        backend=agent_def.backend,
        cli=defaults["cli"],
        resume_flag=defaults["resume_flag"],
        version_command=defaults["version_command"],
        install_hint=defaults["install_hint"],
        model=agent_def.model,
        extra_flags=list(agent_def.extra_flags),
    )


def resolve_all_agents(agents: dict[str, AgentDef]) -> dict[str, AgentConfig]:
    """Resolve all agent definitions from config into runtime AgentConfigs."""
    return {name: resolve_agent(name, adef) for name, adef in agents.items()}


# ---------------------------------------------------------------------------
# Backend-specific response parsers
# ---------------------------------------------------------------------------


def parse_claude_response(stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
    """Parse claude CLI JSON or NDJSON (stream-json) output.

    Single-JSON format (``--output-format json``)::

        {"result": "response text", "session_id": "abc123"}

    NDJSON format (``--output-format stream-json``): one JSON object per line.
    With ``--include-partial-messages``, token deltas are wrapped::

        {"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}, "session_id":"..."}

    Without partial messages, complete text comes via::

        {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}, "session_id":"..."}

    The ``result`` event always carries the final text and session_id.
    """
    raw = stdout
    lines = [ln for ln in stdout.strip().split("\n") if ln.strip()]

    # Single-line: use original single-JSON parser
    if len(lines) <= 1:
        try:
            data = json.loads(stdout)
            if not isinstance(data, dict):
                return stdout.strip(), None, raw
            text = data.get("result", "")
            session_id = data.get("session_id")
            return text, session_id, raw
        except json.JSONDecodeError:
            return stdout.strip(), None, raw

    # Multi-line: parse as NDJSON (stream-json)
    text_parts: list[str] = []
    session_id = None

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")

        # Token-level deltas wrapped in stream_event (--include-partial-messages)
        if event_type == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))
            if not session_id:
                session_id = event.get("session_id")
        # Complete assistant message (without --include-partial-messages)
        elif event_type == "assistant":
            if not text_parts:
                message = event.get("message", {})
                for block in message.get("content", []):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            if not session_id:
                session_id = event.get("session_id")
        elif event_type == "result":
            session_id = event.get("session_id")
            # result event also carries the final text as fallback
            result_text = event.get("result")
            if result_text and not text_parts:
                text_parts.append(result_text)

    return "".join(text_parts), session_id, raw


def parse_codex_response(stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
    """Parse codex JSONL output.

    Extracts thread_id from ``{"type":"thread.started"}`` events and
    response text from ``{"type":"item.completed"}`` events.
    """
    raw = stdout
    thread_id = None
    text_parts: list[str] = []

    for line in stdout.strip().split("\n"):
        if not line:
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                continue

            event_type = event.get("type")

            if event_type == "thread.started":
                thread_id = event.get("thread_id")
            elif event_type == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    text = item.get("text", "")
                    if text:
                        text_parts.append(text)

        except json.JSONDecodeError:
            continue

    return "\n".join(text_parts), thread_id, raw


def parse_cursor_response(stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
    """Parse cursor agent CLI JSON or NDJSON (stream-json) output.

    Single-JSON format: ``{"result": "...", "session_id": "..."}``

    NDJSON format: handles ``stream_event``-wrapped deltas, top-level
    ``content_block_delta``, and ``assistant`` message events.
    """
    raw = stdout
    lines = [ln for ln in stdout.strip().split("\n") if ln.strip()]

    # Single-line: use original single-JSON parser
    if len(lines) <= 1:
        try:
            data = json.loads(stdout)
            if not isinstance(data, dict):
                return stdout.strip(), None, raw
            text = data.get("result") or data.get("text") or data.get("response") or ""
            session_id = data.get("session_id") or data.get("conversation_id")
            return text, session_id, raw
        except json.JSONDecodeError:
            return stdout.strip(), None, raw

    # Multi-line: parse as NDJSON (stream-json)
    delta_parts: list[str] = []
    assistant_parts: list[str] = []
    result_text = ""
    session_id = None

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")

        # Token-level deltas wrapped in stream_event
        if event_type == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    delta_parts.append(delta.get("text", ""))
            if not session_id:
                session_id = event.get("session_id")
        # Top-level content_block_delta (flat format)
        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                delta_parts.append(delta.get("text", ""))
        # Assistant message chunks from --stream-partial-output.
        elif event_type == "assistant":
            message = event.get("message", {})
            chunk_parts: list[str] = []
            if isinstance(message, dict):
                for block in message.get("content", []):
                    if block.get("type") == "text":
                        chunk_parts.append(block.get("text", ""))
            if not chunk_parts:
                text = event.get("text", "")
                if text:
                    chunk_parts.append(text)
            if chunk_parts:
                assistant_parts.append("".join(chunk_parts))
            if not session_id:
                session_id = event.get("session_id") or event.get("conversation_id")
        elif event_type == "result":
            session_id = event.get("session_id") or event.get("conversation_id")
            if event.get("result"):
                result_text = event.get("result")

    if result_text:
        return result_text, session_id, raw
    if delta_parts:
        return "".join(delta_parts), session_id, raw
    if assistant_parts:
        merged = ""
        for part in assistant_parts:
            # Handle cumulative snapshots and chunked fragments.
            if part.startswith(merged):
                merged = part
            elif merged.startswith(part):
                continue
            else:
                merged += part
        return merged, session_id, raw

    return "", session_id, raw


ResponseParser = Callable[[str, str, int], tuple[str, str | None, str]]

RESPONSE_PARSERS: dict[str, ResponseParser] = {
    "claude_code": parse_claude_response,
    "codex": parse_codex_response,
    "cursor": parse_cursor_response,
}


# ---------------------------------------------------------------------------
# Backend-specific command builders
# ---------------------------------------------------------------------------


def build_claude_command(
    config: AgentConfig,
    prompt: str,
    session_id: str | None,
    skip_permissions: bool = True,
    streaming: bool = False,
) -> list[str]:
    """Build claude CLI command.

    Format: ``claude [--dangerously-skip-permissions] [--model MODEL] --print --output-format json [--resume SESSION] -p PROMPT``

    When skip_permissions is False (council queries), restricts to read-only tools.
    When streaming is True, replaces ``--output-format json`` with ``stream-json``
    and appends ``--verbose`` and ``--include-partial-messages``.
    """
    cmd = shlex.split(config.cli)
    if streaming:
        try:
            fmt_idx = cmd.index("--output-format")
            cmd[fmt_idx + 1] = "stream-json"
        except (ValueError, IndexError):
            pass
        cmd.extend(["--verbose", "--include-partial-messages"])
    if skip_permissions:
        cmd.insert(1, "--dangerously-skip-permissions")
    else:
        cmd.extend(["--allowedTools", "Bash", "Read", "Glob", "Grep", "WebFetch", "WebSearch"])
    if config.model:
        cmd.extend(["--model", config.model])
    if config.extra_flags:
        cmd.extend(config.extra_flags)
    if session_id:
        cmd.extend([config.resume_flag, session_id])
    cmd.extend(["-p", prompt])
    return cmd


def build_codex_command(
    config: AgentConfig,
    prompt: str,
    session_id: str | None,
    skip_permissions: bool = True,
    streaming: bool = False,
) -> list[str]:
    """Build codex CLI command.

    Codex uses subcommand-style resume: ``codex exec resume <id> --json <prompt>``

    When skip_permissions is False (council queries), uses read-only sandbox.
    The streaming parameter is accepted but ignored — codex already outputs NDJSON.
    """
    parts = shlex.split(config.cli)
    if skip_permissions:
        parts.insert(1, "--dangerously-bypass-approvals-and-sandbox")
    else:
        parts.extend(["-c", 'sandbox_permissions=["disk-full-read-access"]'])
    if config.model:
        parts.extend(["--model", config.model])
    if config.extra_flags:
        parts.extend(config.extra_flags)
    if session_id:
        try:
            exec_idx = parts.index("exec")
        except ValueError:
            raise ValueError(f"Codex cli must contain 'exec' for session resume, got: {config.cli}") from None
        cmd = [*parts[: exec_idx + 1], config.resume_flag, session_id, *parts[exec_idx + 1 :]]
    else:
        cmd = list(parts)
    cmd.append(prompt)
    return cmd


def build_cursor_command(
    config: AgentConfig,
    prompt: str,
    session_id: str | None,
    skip_permissions: bool = True,
    streaming: bool = False,
) -> list[str]:
    """Build cursor agent CLI command.

    Format: ``agent [--force --sandbox disabled] [--model MODEL] --print --output-format json PROMPT [--resume SESSION]``

    When skip_permissions is False (council queries), uses --mode ask for read-only.
    When streaming is True, replaces ``--output-format json`` with ``stream-json``
    and enables ``--stream-partial-output`` so Cursor emits incremental deltas.
    """
    cmd = shlex.split(config.cli)
    if streaming:
        try:
            fmt_idx = cmd.index("--output-format")
            cmd[fmt_idx + 1] = "stream-json"
        except (ValueError, IndexError):
            pass
        cmd.append("--stream-partial-output")
    if skip_permissions:
        cmd.insert(1, "--force")
        cmd.insert(2, "--sandbox")
        cmd.insert(3, "disabled")
    else:
        cmd.extend(["--mode", "ask"])
    if config.model:
        cmd.extend(["--model", config.model])
    if config.extra_flags:
        cmd.extend(config.extra_flags)
    cmd.append(prompt)
    if session_id:
        cmd.extend([config.resume_flag, session_id])
    return cmd


CommandBuilder = Callable[[AgentConfig, str, str | None, bool, bool], list[str]]

COMMAND_BUILDERS: dict[str, CommandBuilder] = {
    "claude_code": build_claude_command,
    "codex": build_codex_command,
    "cursor": build_cursor_command,
}


def clean_agent_env(role: str | None = None, agent_name: str | None = None) -> dict[str, str]:
    """Return an env dict safe for spawning agent CLI subprocesses.

    Strips ``CLAUDECODE`` so child ``claude`` processes don't refuse to start
    with a "nested session" error when ``kd`` is invoked from inside Claude Code.

    Optionally injects ``KD_ROLE`` and ``KD_AGENT_NAME`` for ``kd whoami``.
    """
    import os

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    if role:
        env["KD_ROLE"] = role
    if agent_name:
        env["KD_AGENT_NAME"] = agent_name
    return env


def build_command(
    config: AgentConfig,
    prompt: str,
    session_id: str | None = None,
    skip_permissions: bool = True,
    streaming: bool = False,
) -> list[str]:
    """Build a CLI command for an agent.

    Dispatches to backend-specific command builder.

    Raises:
        ValueError: If the backend is unknown.
    """
    builder = COMMAND_BUILDERS.get(config.backend)
    if builder is None:
        raise ValueError(f"Unknown backend: {config.backend}")
    return builder(config, prompt, session_id, skip_permissions, streaming=streaming)


def parse_response(config: AgentConfig, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
    """Parse response from an agent's CLI output.

    Dispatches to backend-specific response parser. Falls back to
    returning raw stdout for unknown backends.
    """
    parser = RESPONSE_PARSERS.get(config.backend)
    if parser is None:
        return stdout.strip(), None, stdout
    return parser(stdout, stderr, code)


# ---------------------------------------------------------------------------
# Stream text extractors — extract text from individual NDJSON lines
# ---------------------------------------------------------------------------


def extract_claude_stream_text(line: str) -> str | None:
    """Extract text from a single Claude stream-json NDJSON line.

    Handles both the ``stream_event`` wrapper (``--include-partial-messages``)
    and bare ``content_block_delta`` events.  Returns None for non-text events.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    # Unwrap stream_event wrapper
    if event.get("type") == "stream_event":
        event = event.get("event", {})
    if event.get("type") == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            return delta.get("text")
    return None


def extract_codex_stream_text(line: str) -> str | None:
    """Extract text from a single Codex NDJSON line.

    Returns agent message text from ``item.completed`` events, or None.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    if event.get("type") == "item.completed":
        item = event.get("item", {})
        if item.get("type") == "agent_message":
            return item.get("text")
    return None


def extract_cursor_stream_text(line: str) -> str | None:
    """Extract text from a single Cursor stream-json NDJSON line.

    Handles ``stream_event`` wrapper, bare ``content_block_delta`` events,
    and chunked ``assistant`` events.
    Returns None for non-text events.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    # Unwrap stream_event wrapper
    if event.get("type") == "stream_event":
        event = event.get("event", {})
    if event.get("type") == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            return delta.get("text")
    if event.get("type") == "assistant":
        message = event.get("message", {})
        if isinstance(message, dict):
            parts: list[str] = []
            for block in message.get("content", []):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            if parts:
                return "".join(parts)
        text = event.get("text")
        if isinstance(text, str) and text:
            return text
    return None


StreamExtractor = Callable[[str], str | None]

STREAM_TEXT_EXTRACTORS: dict[str, StreamExtractor] = {
    "claude_code": extract_claude_stream_text,
    "codex": extract_codex_stream_text,
    "cursor": extract_cursor_stream_text,
}


def extract_stream_text(line: str, backend: str) -> str | None:
    """Extract text from a single NDJSON line for the given backend.

    Returns None for non-text events or unknown backends.
    """
    extractor = STREAM_TEXT_EXTRACTORS.get(backend)
    if extractor is None:
        return None
    return extractor(line)


# ---------------------------------------------------------------------------
# Stream thinking extractors — extract thinking/reasoning tokens from NDJSON
# ---------------------------------------------------------------------------


def extract_cursor_stream_thinking(line: str) -> str | None:
    """Extract thinking text from a Cursor stream-json NDJSON line.

    Cursor emits ``{"type": "thinking", "subtype": "delta", "text": "..."}``
    for reasoning tokens.  Returns None for non-thinking events.
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    if event.get("type") == "thinking" and event.get("subtype") == "delta":
        text = event.get("text")
        if isinstance(text, str):
            return text
    return None


def extract_codex_stream_thinking(line: str) -> str | None:
    """Extract reasoning text from a single Codex NDJSON line.

    Codex emits reasoning chunks via:
    ``{"type":"item.completed","item":{"type":"reasoning","text":"..."}}``
    """
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    if event.get("type") == "item.completed":
        item = event.get("item", {})
        if item.get("type") == "reasoning":
            text = item.get("text")
            if isinstance(text, str):
                return text
    return None


STREAM_THINKING_EXTRACTORS: dict[str, StreamExtractor] = {
    "codex": extract_codex_stream_thinking,
    "cursor": extract_cursor_stream_thinking,
}


def extract_stream_thinking(line: str, backend: str) -> str | None:
    """Extract thinking text from a single NDJSON line for the given backend.

    Returns None for non-thinking events, unknown backends, or backends
    that don't emit thinking tokens (e.g. claude_code).
    """
    extractor = STREAM_THINKING_EXTRACTORS.get(backend)
    if extractor is None:
        return None
    return extractor(line)
