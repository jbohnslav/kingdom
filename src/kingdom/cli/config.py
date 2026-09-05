"""Config and doctor CLI commands."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer

from kingdom.agent import AgentConfig, clean_agent_env

from .display import styled_echo
from .helpers import require_project_root, verbose_echo

config_app = typer.Typer(name="config", help="View and manage configuration.")


@dataclass(frozen=True)
class AgentRuntimeCheck:
    """Credential-free summary of a provider CLI runtime check."""

    status: str
    version: str | None = None
    error: str | None = None
    recovery: str = ""


AUTH_COMMANDS = {
    "claude_code": ["auth", "status", "--json"],
    "codex": ["login", "status"],
    "cursor": ["status"],
}

AUTH_RECOVERY = {
    "claude_code": "Run `claude` to re-authenticate, then run `kd doctor`.",
    "codex": "Run `codex login` to re-authenticate, then run `kd doctor`.",
    "cursor": "Run `agent login` to re-authenticate, then run `kd doctor`.",
}

CATALOG_COMMANDS = {
    "codex": ["debug", "models"],
    "cursor": ["models"],
}

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@config_app.command("show", help="Print the effective configuration.")
def config_show() -> None:
    """Print the effective config with source annotations (config file vs defaults)."""
    import dataclasses

    from kingdom.config import config_source_path, load_config, load_raw_config

    base = require_project_root()
    try:
        config_path = config_source_path(base)
        cfg = load_config(base, config_path=config_path)
    except ValueError as e:
        styled_echo(f"Error: invalid config — {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    raw = load_raw_config(base, config_path=config_path)

    verbose_echo(f"base: {base}")
    verbose_echo(f"config path: {config_path} ({'exists' if config_path.exists() else 'not found'})")
    source_status = "config file" if config_path.exists() else "not found; built-in defaults"
    typer.echo(f"Config source: {config_path} ({source_status})")

    def flatten(obj, prefix=""):
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                items.extend(flatten(v, f"{prefix}{k}."))
        elif isinstance(obj, list):
            items.append((prefix.rstrip("."), ", ".join(str(x) for x in obj)))
        else:
            items.append((prefix.rstrip("."), obj))
        return items

    def is_in_raw(dotted_key: str) -> bool:
        """Check if a dotted key was explicitly set in the config file.

        Tries all possible split points to handle keys containing dots
        (e.g. agent names like 'gpt.4o').
        """

        def walk(key: str, node: dict) -> bool:
            if not isinstance(node, dict):
                return False
            # Try each possible split: first segment as dict key, rest recursed
            for i in range(1, len(key) + 1):
                prefix = key[:i]
                rest = key[i + 1 :]  # skip the dot
                if prefix in node:
                    if not rest:
                        return True
                    if walk(rest, node[prefix]):
                        return True
            return False

        if walk(dotted_key, raw):
            return True
        if dotted_key.endswith(".effort"):
            legacy_key = f"{dotted_key.rsplit('.', 1)[0]}.reasoning_effort"
            return walk(legacy_key, raw)
        return False

    effective = dataclasses.asdict(cfg)
    entries = flatten(effective)

    # Filter out empty values (empty strings, empty lists, empty dicts)
    entries = [(k, v) for k, v in entries if v not in ("", [], {}, None)]

    if not entries:
        typer.echo("(all defaults, no config file)")
        return

    key_width = max(len(k) for k, _ in entries)
    for key, value in entries:
        source = "config" if is_in_raw(key) else "default"
        color = typer.colors.CYAN if source == "config" else None
        styled_echo(f"  {key:<{key_width}}  {value!s}  ({source})", fg=color)


def check_cli(command: list[str]) -> tuple[bool, str | None]:
    """Check if a CLI command is available."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except FileNotFoundError:
        return (False, "Command not found")
    except subprocess.TimeoutExpired:
        return (False, "Command timed out")
    except OSError as exc:
        return (False, f"Could not run command: {exc}")
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or f"Command exited with status {result.returncode}"
        return (False, error)
    return (True, None)


def authentication_succeeded(backend: str, stdout: str) -> bool | None:
    """Interpret successful auth-status output without retaining account details."""
    if backend == "claude_code":
        try:
            status = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        return status.get("loggedIn") if isinstance(status, dict) else None

    normalized = " ".join(stdout.lower().split())
    return not any(marker in normalized for marker in ("not logged in", "not authenticated", "unauthorized"))


def check_agent_runtime(agent: AgentConfig) -> AgentRuntimeCheck:
    """Check one configured provider's executable, version, and authentication."""
    version_command = shlex.split(agent.version_command or f"{shlex.split(agent.cli)[0]} --version")
    env = clean_agent_env(role="doctor", agent_name=agent.name)
    try:
        version_result = subprocess.run(
            version_command,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
    except FileNotFoundError:
        return AgentRuntimeCheck(status="missing", error="Command not found", recovery=agent.install_hint)
    except subprocess.TimeoutExpired:
        return AgentRuntimeCheck(
            status="version_failed",
            error="Version probe timed out",
            recovery=f"Reinstall or update the {agent.backend} CLI, then run `kd doctor`.",
        )
    except OSError:
        return AgentRuntimeCheck(
            status="version_failed",
            error="Version probe could not run",
            recovery=f"Reinstall or update the {agent.backend} CLI, then run `kd doctor`.",
        )

    if version_result.returncode != 0:
        return AgentRuntimeCheck(
            status="version_failed",
            error=f"Version probe exited with status {version_result.returncode}",
            recovery=f"Reinstall or update the {agent.backend} CLI, then run `kd doctor`.",
        )

    version_output = version_result.stdout.strip() or version_result.stderr.strip()
    version = version_output.splitlines()[0] if version_output else "unknown"
    auth_command = AUTH_COMMANDS.get(agent.backend)
    if auth_command is None:
        return AgentRuntimeCheck(status="available", version=version)

    executable = shlex.split(agent.cli)[0]
    try:
        auth_result = subprocess.run(
            [executable, *auth_command],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return AgentRuntimeCheck(
            status="runtime_failed",
            version=version,
            error="Authentication probe timed out",
            recovery=f"Run `{executable} {' '.join(auth_command)}` directly, then run `kd doctor`.",
        )
    except OSError:
        return AgentRuntimeCheck(
            status="runtime_failed",
            version=version,
            error="Authentication probe could not run",
            recovery=f"Run `{executable} {' '.join(auth_command)}` directly, then run `kd doctor`.",
        )

    authenticated = authentication_succeeded(agent.backend, auth_result.stdout)
    output = f"{auth_result.stdout}\n{auth_result.stderr}".lower()
    auth_marker = any(marker in output for marker in ("not logged in", "not authenticated", "unauthorized", "401"))
    if authenticated is False or (auth_result.returncode != 0 and auth_marker):
        return AgentRuntimeCheck(
            status="authentication_failed",
            version=version,
            error="Provider authentication is unavailable",
            recovery=AUTH_RECOVERY[agent.backend],
        )
    if auth_result.returncode != 0 or authenticated is None:
        detail = (
            f"Authentication probe exited with status {auth_result.returncode}"
            if auth_result.returncode
            else "Authentication probe returned an unsupported response"
        )
        return AgentRuntimeCheck(
            status="runtime_failed",
            version=version,
            error=detail,
            recovery=f"Run `{executable} {' '.join(auth_command)}` directly, then run `kd doctor`.",
        )
    return AgentRuntimeCheck(status="available", version=version)


def cursor_catalog_models(stdout: str) -> set[str]:
    """Extract stable CLI model identifiers from Cursor's human-readable list."""
    models: set[str] = set()
    for raw_line in stdout.splitlines():
        line = ANSI_ESCAPE.sub("", raw_line).strip().lstrip("-*• ").strip()
        if not line or line.lower().startswith(("loading ", "available models", "no models available")):
            continue
        models.add(line.split()[0])
    return models


def check_agent_model(agent: AgentConfig) -> tuple[str, str | None]:
    """Validate a pinned model when its provider exposes an account catalog."""
    if not agent.model:
        return "unchecked", None

    catalog_command = CATALOG_COMMANDS.get(agent.backend)
    if catalog_command is None:
        return "unchecked", None

    executable = shlex.split(agent.cli)[0]
    env = clean_agent_env(role="doctor", agent_name=agent.name)
    try:
        result = subprocess.run(
            [executable, *catalog_command],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
    except OSError:
        return "unchecked", f"Could not run {agent.backend} model catalog discovery"
    except subprocess.TimeoutExpired:
        return "unchecked", f"{agent.backend} model catalog discovery timed out"

    if result.returncode != 0:
        return "unchecked", f"{agent.backend} model catalog command exited with status {result.returncode}"

    if agent.backend == "cursor":
        models = cursor_catalog_models(result.stdout)
        if agent.model not in models:
            return "unavailable", f"Model '{agent.model}' is not available to this Cursor account"
        return "available", None

    try:
        catalog = json.loads(result.stdout)
        models = catalog.get("models", [])
        model = next(
            (entry for entry in models if isinstance(entry, dict) and entry.get("slug") == agent.model),
            None,
        )
    except (json.JSONDecodeError, AttributeError, TypeError):
        return "unchecked", "Codex model catalog returned an unsupported response"
    if model is None:
        return "unavailable", f"Model '{agent.model}' is not available to this Codex account"

    supported_efforts = {
        level.get("effort") for level in model.get("supported_reasoning_levels", []) if isinstance(level, dict)
    }
    if agent.effort and supported_efforts and agent.effort not in supported_efforts:
        return "unavailable", f"Model '{agent.model}' does not support effort '{agent.effort}'"
    return "available", None


def get_doctor_checks(base: Path, *, config_path: Path | None = None) -> list[dict[str, object]]:
    """Build doctor checks from agent configs."""
    from kingdom.agent import resolve_all_agents
    from kingdom.config import load_config

    cfg = load_config(base, config_path=config_path)
    agents = resolve_all_agents(cfg.agents)
    active_names = {
        *cfg.council.members,
        *cfg.council.review_members,
        cfg.peasant.agent,
        cfg.lord.agent,
    }

    checks: list[dict[str, object]] = []
    for agent in agents.values():
        if agent.name not in active_names:
            continue
        version_cmd = agent.version_command or f"{shlex.split(agent.cli)[0]} --version"
        checks.append(
            {
                "name": agent.name,
                "command": shlex.split(version_cmd),
                "install_hint": agent.install_hint or f"Install {agent.name}",
                "model": agent.model or "inherited",
                "model_source": "configured" if agent.model else "provider",
                "effort": agent.effort or "inherited",
                "effort_source": "configured" if agent.effort else "provider",
                "agent": agent,
            }
        )
    return checks


def check_config(base: Path, *, config_path: Path | None = None) -> tuple[bool, str | None]:
    """Validate .kd/config.json and return (ok, error_message).

    Returns (True, None) if config is valid or doesn't exist.
    Returns (False, message) if config has errors.
    """
    from kingdom.config import config_source_path, load_config

    config_path = config_path or config_source_path(base)
    if not config_path.exists():
        return True, None

    try:
        load_config(base, config_path=config_path)
        return True, None
    except ValueError as e:
        return False, str(e)
