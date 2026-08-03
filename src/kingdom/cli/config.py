"""Config and doctor CLI commands."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import typer

from kingdom.agent import AgentConfig, clean_agent_env

from .display import styled_echo
from .helpers import require_project_root, verbose_echo

config_app = typer.Typer(name="config", help="View and manage configuration.")


@config_app.command("show", help="Print the effective configuration.")
def config_show() -> None:
    """Print the effective config with source annotations (config file vs defaults)."""
    import dataclasses

    from kingdom.config import load_config, load_raw_config

    base = require_project_root()
    try:
        cfg = load_config(base)
    except ValueError as e:
        styled_echo(f"Error: invalid config — {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    raw = load_raw_config(base)

    verbose_echo(f"base: {base}")
    config_path = base / ".kd" / "config.json"
    verbose_echo(f"config path: {config_path} ({'exists' if config_path.exists() else 'not found'})")

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


def check_agent_model(agent: AgentConfig) -> tuple[str, str | None]:
    """Validate a pinned Codex model against the account-visible catalog."""
    if agent.backend != "codex" or not agent.model:
        return "unchecked", None

    executable = shlex.split(agent.cli)[0]
    env = clean_agent_env(role="doctor", agent_name=agent.name)
    try:
        result = subprocess.run(
            [executable, "debug", "models"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
    except OSError:
        return "unavailable", "Codex CLI not found"
    except subprocess.TimeoutExpired:
        return "unavailable", "Codex model catalog timed out"

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
        return "unavailable", f"Could not read Codex model catalog: {error}"

    try:
        models = json.loads(result.stdout).get("models", [])
    except (json.JSONDecodeError, AttributeError):
        return "unavailable", "Codex model catalog returned invalid JSON"

    model = next(
        (entry for entry in models if isinstance(entry, dict) and entry.get("slug") == agent.model),
        None,
    )
    if model is None:
        return "unavailable", f"Model '{agent.model}' is not available to this Codex account"

    supported_efforts = {
        level.get("effort") for level in model.get("supported_reasoning_levels", []) if isinstance(level, dict)
    }
    if agent.effort and supported_efforts and agent.effort not in supported_efforts:
        return "unavailable", f"Model '{agent.model}' does not support effort '{agent.effort}'"
    return "available", None


def get_doctor_checks(base: Path) -> list[dict[str, object]]:
    """Build doctor checks from agent configs."""
    from kingdom.agent import resolve_all_agents
    from kingdom.config import load_config

    cfg = load_config(base)
    agents = resolve_all_agents(cfg.agents)

    checks: list[dict[str, object]] = []
    for agent in agents.values():
        version_cmd = agent.version_command or f"{shlex.split(agent.cli)[0]} --version"
        checks.append(
            {
                "name": agent.name,
                "command": shlex.split(version_cmd),
                "install_hint": agent.install_hint or f"Install {agent.name}",
                "model": agent.model or "inherited",
                "model_source": "configured" if agent.model else "provider",
                "effort": agent.effort or "inherited",
                "agent": agent,
            }
        )
    return checks


def check_config(base: Path) -> tuple[bool, str | None]:
    """Validate .kd/config.json and return (ok, error_message).

    Returns (True, None) if config is valid or doesn't exist.
    Returns (False, message) if config has errors.
    """
    from kingdom.config import load_config
    from kingdom.state import state_root

    config_path = state_root(base) / "config.json"
    if not config_path.exists():
        return True, None

    try:
        load_config(base)
        return True, None
    except ValueError as e:
        return False, str(e)
