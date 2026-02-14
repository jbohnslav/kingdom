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
from dataclasses import dataclass, field
from typing import Any

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
    """Parse claude CLI JSON output.

    Expected format::

        {"result": "response text", "session_id": "abc123"}
    """
    raw = stdout
    try:
        data = json.loads(stdout)
        if not isinstance(data, dict):
            return stdout.strip(), None, raw
        text = data.get("result", "")
        session_id = data.get("session_id")
        return text, session_id, raw
    except json.JSONDecodeError:
        return stdout.strip(), None, raw


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
    """Parse cursor agent CLI JSON output."""
    raw = stdout
    try:
        data = json.loads(stdout)
        if not isinstance(data, dict):
            return stdout.strip(), None, raw
        text = data.get("result") or data.get("text") or data.get("response") or ""
        session_id = data.get("session_id") or data.get("conversation_id")
        return text, session_id, raw
    except json.JSONDecodeError:
        return stdout.strip(), None, raw


RESPONSE_PARSERS: dict[str, Any] = {
    "claude_code": parse_claude_response,
    "codex": parse_codex_response,
    "cursor": parse_cursor_response,
}


# ---------------------------------------------------------------------------
# Backend-specific command builders
# ---------------------------------------------------------------------------


def build_claude_command(
    config: AgentConfig, prompt: str, session_id: str | None, skip_permissions: bool = True
) -> list[str]:
    """Build claude CLI command.

    Format: ``claude [--dangerously-skip-permissions] [--model MODEL] --print --output-format json [--resume SESSION] -p PROMPT``

    When skip_permissions is False (council queries), restricts to read-only tools.
    """
    cmd = shlex.split(config.cli)
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
    config: AgentConfig, prompt: str, session_id: str | None, skip_permissions: bool = True
) -> list[str]:
    """Build codex CLI command.

    Codex uses subcommand-style resume: ``codex exec resume <id> --json <prompt>``

    When skip_permissions is False (council queries), uses read-only sandbox.
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
    config: AgentConfig, prompt: str, session_id: str | None, skip_permissions: bool = True
) -> list[str]:
    """Build cursor agent CLI command.

    Format: ``agent [--force --sandbox disabled] [--model MODEL] --print --output-format json PROMPT [--resume SESSION]``

    When skip_permissions is False (council queries), uses --mode ask for read-only.
    """
    cmd = shlex.split(config.cli)
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


COMMAND_BUILDERS: dict[str, Any] = {
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
    config: AgentConfig, prompt: str, session_id: str | None = None, skip_permissions: bool = True
) -> list[str]:
    """Build a CLI command for an agent.

    Dispatches to backend-specific command builder.

    Raises:
        ValueError: If the backend is unknown.
    """
    builder = COMMAND_BUILDERS.get(config.backend)
    if builder is None:
        raise ValueError(f"Unknown backend: {config.backend}")
    return builder(config, prompt, session_id, skip_permissions)


def parse_response(config: AgentConfig, stdout: str, stderr: str, code: int) -> tuple[str, str | None, str]:
    """Parse response from an agent's CLI output.

    Dispatches to backend-specific response parser. Falls back to
    returning raw stdout for unknown backends.
    """
    parser = RESPONSE_PARSERS.get(config.backend)
    if parser is None:
        return stdout.strip(), None, stdout
    return parser(stdout, stderr, code)
