"""Agent configuration model.

Agent definitions are markdown files with YAML frontmatter, stored at
``.kd/agents/<name>.md``. Each agent specifies a backend (claude_code, codex,
cursor), CLI command, and session resume flag.

Example agent file::

    ---
    name: claude
    backend: claude_code
    cli: claude --print --output-format json
    resume_flag: --resume
    version_command: claude --version
    install_hint: Install Claude Code: https://docs.anthropic.com/en/docs/claude-code
    ---
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from kingdom.parsing import parse_frontmatter
from kingdom.state import state_root


@dataclass
class AgentConfig:
    """Configuration for an agent, loaded from .kd/agents/<name>.md."""

    name: str
    backend: str  # claude_code, codex, cursor
    cli: str  # base CLI command (e.g., "claude --print --output-format json")
    resume_flag: str  # session resume mechanism (e.g., "--resume" or "resume")
    version_command: str = ""  # command for `kd doctor` checks
    install_hint: str = ""  # help text when CLI is missing


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def agents_root(base: Path) -> Path:
    """Return path to .kd/agents/."""
    return state_root(base) / "agents"


# ---------------------------------------------------------------------------
# Config file I/O
# ---------------------------------------------------------------------------


def parse_agent_file(content: str) -> AgentConfig:
    """Parse an agent .md file (YAML frontmatter) into AgentConfig.

    Raises:
        ValueError: If frontmatter is missing or required fields are absent.
    """
    fm, _ = parse_frontmatter(content)

    name = fm.get("name")
    backend = fm.get("backend")
    cli = fm.get("cli")

    if not name or not backend or not cli:
        raise ValueError("Agent file must have name, backend, and cli fields")

    return AgentConfig(
        name=str(name),
        backend=str(backend),
        cli=str(cli),
        resume_flag=str(fm.get("resume_flag", "") or ""),
        version_command=str(fm.get("version_command", "") or ""),
        install_hint=str(fm.get("install_hint", "") or ""),
    )


def serialize_agent_file(config: AgentConfig) -> str:
    """Serialize an AgentConfig to .md file format."""
    lines = ["---"]
    lines.append(f"name: {config.name}")
    lines.append(f"backend: {config.backend}")
    lines.append(f"cli: {config.cli}")
    lines.append(f"resume_flag: {config.resume_flag}")
    if config.version_command:
        lines.append(f"version_command: {config.version_command}")
    if config.install_hint:
        lines.append(f"install_hint: {config.install_hint}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def load_agent(name: str, base: Path) -> AgentConfig:
    """Load an agent config from .kd/agents/<name>.md.

    Raises:
        FileNotFoundError: If the agent file doesn't exist.
    """
    path = agents_root(base) / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Agent config not found: {path}")
    content = path.read_text(encoding="utf-8")
    return parse_agent_file(content)


def list_agents(base: Path) -> list[AgentConfig]:
    """List all registered agent configs from .kd/agents/."""
    root = agents_root(base)
    if not root.exists():
        return []

    configs: list[AgentConfig] = []
    for path in sorted(root.glob("*.md")):
        try:
            configs.append(parse_agent_file(path.read_text(encoding="utf-8")))
        except (ValueError, FileNotFoundError):
            continue
    return configs


# ---------------------------------------------------------------------------
# Default agent configurations
# ---------------------------------------------------------------------------

DEFAULT_AGENTS: dict[str, AgentConfig] = {
    "claude": AgentConfig(
        name="claude",
        backend="claude_code",
        cli="claude --print --output-format json",
        resume_flag="--resume",
        version_command="claude --version",
        install_hint="Install Claude Code: https://docs.anthropic.com/en/docs/claude-code",
    ),
    "codex": AgentConfig(
        name="codex",
        backend="codex",
        cli="codex exec --json",
        resume_flag="resume",
        version_command="codex --version",
        install_hint="Install Codex CLI: npm install -g @openai/codex",
    ),
    "cursor": AgentConfig(
        name="cursor",
        backend="cursor",
        cli="agent --print --output-format json",
        resume_flag="--resume",
        version_command="agent --version",
        install_hint="Install Cursor Agent: https://docs.cursor.com/agent",
    ),
}


def create_default_agent_files(base: Path) -> list[Path]:
    """Create default agent .md files in .kd/agents/. Idempotent."""
    root = agents_root(base)
    root.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for config in DEFAULT_AGENTS.values():
        path = root / f"{config.name}.md"
        if not path.exists():
            path.write_text(serialize_agent_file(config), encoding="utf-8")
        paths.append(path)
    return paths


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


RESPONSE_PARSERS = {
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

    Format: ``claude [--dangerously-skip-permissions] --print --output-format json [--resume SESSION] -p PROMPT``

    When skip_permissions is False (council queries), restricts to read-only tools.
    """
    cmd = shlex.split(config.cli)
    if skip_permissions:
        cmd.insert(1, "--dangerously-skip-permissions")
    else:
        cmd.extend(["--allowedTools", "Read", "Glob", "Grep", "WebFetch", "WebSearch"])
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

    Format: ``agent [--force --sandbox disabled] --print --output-format json PROMPT [--resume SESSION]``

    When skip_permissions is False (council queries), uses --mode ask for read-only.
    """
    cmd = shlex.split(config.cli)
    if skip_permissions:
        cmd.insert(1, "--force")
        cmd.insert(2, "--sandbox")
        cmd.insert(3, "disabled")
    else:
        cmd.extend(["--mode", "ask"])
    cmd.append(prompt)
    if session_id:
        cmd.extend([config.resume_flag, session_id])
    return cmd


COMMAND_BUILDERS = {
    "claude_code": build_claude_command,
    "codex": build_codex_command,
    "cursor": build_cursor_command,
}


def clean_agent_env() -> dict[str, str]:
    """Return an env dict safe for spawning agent CLI subprocesses.

    Strips ``CLAUDECODE`` so child ``claude`` processes don't refuse to start
    with a "nested session" error when ``kd`` is invoked from inside Claude Code.
    """
    import os

    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def build_command(
    config: AgentConfig, prompt: str, session_id: str | None = None, skip_permissions: bool = True
) -> list[str]:
    """Build a CLI command for an agent.

    Dispatches to backend-specific command builder.

    Args:
        config: Agent configuration.
        prompt: The prompt text.
        session_id: Optional session ID for resume.
        skip_permissions: If True (default), insert flags to bypass permission prompts.
            Set to False for read-only council queries.

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
