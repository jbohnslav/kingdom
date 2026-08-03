"""Plugin management CLI commands."""

from __future__ import annotations

import json
import subprocess
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from kingdom.codex_plugin import (
    codex_plugin_marketplace_name,
    install_codex_plugin,
    is_codex_plugin_configured,
    uninstall_codex_plugin,
)

from .display import print_error, styled_echo

plugin_app = typer.Typer(name="plugin", help="Manage Kingdom agent-host integrations.")


class PluginHost(StrEnum):
    """Agent hosts whose plugin state Kingdom can inspect."""

    CLAUDE = "claude"
    CODEX = "codex"


class PluginInstallHost(StrEnum):
    """Hosts with an explicit plugin-package installer."""

    CODEX = "codex"


HOOK_COMMAND = "kd hook run"
LEGACY_HOOK_COMMANDS = {
    '"$CLAUDE_PROJECT_DIR"/.claude/hooks/kd-workflow.sh',
    "$CLAUDE_PROJECT_DIR/.claude/hooks/kd-workflow.sh",
    ".claude/hooks/kd-workflow.sh",
}

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop")
EXTENDED_HOOK_EVENTS = ("SessionEnd", "PreCompact", "PostCompact", "SubagentStart", "SubagentStop")
SUPPORTED_HOOK_EVENTS = HOOK_EVENTS + EXTENDED_HOOK_EVENTS

HOOK_CONFIG = {
    "matcher": "",
    "hooks": [
        {
            "type": "command",
            "command": HOOK_COMMAND,
            "timeout": 10,
        }
    ],
}


def find_git_root() -> Path:
    """Find the git repository root directory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        msg = "Not inside a git repository."
        raise ValueError(msg)
    return Path(result.stdout.strip())


def read_settings(settings_path: Path) -> dict:
    """Read .claude/settings.json, returning empty dict if missing or malformed."""
    if settings_path.exists():
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in {settings_path}: {exc}") from None
    return {}


def write_settings(settings_path: Path, settings: dict) -> None:
    """Write .claude/settings.json with consistent formatting."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def has_hook_for_event(settings: dict, event: str) -> bool:
    """Check if the kingdom hook is present for a given event."""
    event_hooks = settings.get("hooks", {}).get(event, [])
    return any(any(h.get("command") == HOOK_COMMAND for h in matcher.get("hooks", [])) for matcher in event_hooks)


def is_hook_installed(settings: dict) -> bool:
    """Check if the legacy/core kingdom hooks are present."""
    return all(has_hook_for_event(settings, event) for event in HOOK_EVENTS)


def has_full_hook_installation(settings: dict) -> bool:
    """Check if the full supported Claude lifecycle hook set is installed."""
    return all(has_hook_for_event(settings, event) for event in SUPPORTED_HOOK_EVENTS)


def has_legacy_hook_installation(settings: dict) -> bool:
    hooks = settings.get("hooks", {})
    return any(
        hook.get("command") in LEGACY_HOOK_COMMANDS
        for matchers in hooks.values()
        for matcher in matchers
        for hook in matcher.get("hooks", [])
    )


def remove_legacy_hook_installation(settings: dict) -> bool:
    hooks = settings.get("hooks", {})
    changed = False
    for event, matchers in list(hooks.items()):
        retained_matchers = []
        for matcher in matchers:
            retained_hooks = [
                hook for hook in matcher.get("hooks", []) if hook.get("command") not in LEGACY_HOOK_COMMANDS
            ]
            if len(retained_hooks) != len(matcher.get("hooks", [])):
                changed = True
            if retained_hooks:
                retained_matcher = dict(matcher)
                retained_matcher["hooks"] = retained_hooks
                retained_matchers.append(retained_matcher)
        if retained_matchers:
            hooks[event] = retained_matchers
        else:
            hooks.pop(event, None)
    if not hooks:
        settings.pop("hooks", None)
    return changed


def activate_codex_plugin(marketplace_name: str) -> tuple[bool, str]:
    """Install the refreshed Kingdom source through Codex's marketplace CLI."""
    try:
        result = subprocess.run(
            ["codex", "plugin", "add", f"kingdom@{marketplace_name}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return False, "Codex CLI was not found; install it, then rerun this command."
    except subprocess.TimeoutExpired:
        return False, "Codex plugin installation timed out."
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        return False, output or "Codex plugin installation failed."
    return True, output or "Codex plugin activated."


def deactivate_codex_plugin(marketplace_name: str) -> tuple[bool, str]:
    """Remove Kingdom from Codex before cleaning its managed local source."""
    try:
        result = subprocess.run(
            ["codex", "plugin", "remove", f"kingdom@{marketplace_name}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return False, "Codex CLI was not found; install it, then rerun this command."
    except subprocess.TimeoutExpired:
        return False, "Codex plugin removal timed out."
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        return False, output or "Codex plugin removal failed."
    return True, output or "Codex plugin deactivated."


@plugin_app.command("install", help="Install a Kingdom integration for an agent host.")
def plugin_install(host: PluginInstallHost) -> None:
    """Install the Codex plugin source, marketplace entry, skill, and hooks."""
    try:
        result = install_codex_plugin(Path.home())
    except (OSError, RuntimeError, ValueError) as exc:
        print_error(f"Could not install the Codex plugin: {exc}")
        raise typer.Exit(code=1) from None

    activated, activation_message = activate_codex_plugin(result.marketplace_name)
    if not activated:
        print_error(activation_message)
        typer.echo(f"Plugin source remains available at {result.plugin_root}")
        raise typer.Exit(code=1)

    styled_echo(f"Kingdom Codex plugin {result.status}.", fg=typer.colors.GREEN)
    typer.echo(f"  Plugin: {result.plugin_root}")
    typer.echo(f"  Marketplace: {result.marketplace_path}")
    typer.echo("  Preserved other marketplace entries and Codex configuration.")
    if activation_message:
        typer.echo(f"  Codex: {activation_message}")
    typer.echo("Start a new Codex task, open `/hooks`, and trust the Kingdom hooks when prompted.")


@plugin_app.command("uninstall", help="Uninstall a Kingdom integration for an agent host.")
def plugin_uninstall(host: PluginInstallHost) -> None:
    """Deactivate Codex, then remove only unmodified Kingdom-managed files."""
    home = Path.home()
    try:
        marketplace_name = codex_plugin_marketplace_name(home)
    except (OSError, ValueError) as exc:
        print_error(f"Could not inspect the Codex plugin: {exc}")
        raise typer.Exit(code=1) from None
    if marketplace_name is None:
        styled_echo("Kingdom Codex plugin is not configured.", fg=typer.colors.YELLOW)
        return

    deactivated, deactivation_message = deactivate_codex_plugin(marketplace_name)
    if not deactivated:
        print_error(deactivation_message)
        typer.echo("Local Kingdom plugin state was left unchanged.")
        raise typer.Exit(code=1)

    try:
        result = uninstall_codex_plugin(home)
    except (OSError, RuntimeError, ValueError) as exc:
        print_error(f"Codex was deactivated, but local plugin cleanup failed: {exc}")
        raise typer.Exit(code=1) from None

    styled_echo("Kingdom Codex plugin uninstalled.", fg=typer.colors.GREEN)
    typer.echo(f"  Plugin: {result.plugin_root}")
    typer.echo(f"  Marketplace: {result.marketplace_path}")
    typer.echo(f"  Removed {len(result.removed_files)} managed file(s).")
    if result.preserved_files:
        typer.echo(f"  Preserved local files: {', '.join(result.preserved_files)}")
    typer.echo(f"  Codex: {deactivation_message}")


@plugin_app.command("enable", help="Install the kingdom workflow hook into Claude Code.")
def plugin_enable() -> None:
    """Add the kingdom hooks to .claude/settings.json."""
    try:
        git_root = find_git_root()
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    settings_path = git_root / ".claude" / "settings.json"
    settings = read_settings(settings_path)

    removed_legacy = remove_legacy_hook_installation(settings)
    if has_full_hook_installation(settings) and not removed_legacy:
        styled_echo("Kingdom hook is already enabled.", fg=typer.colors.YELLOW)
        return

    hooks = settings.setdefault("hooks", {})
    for event in SUPPORTED_HOOK_EVENTS:
        if not has_hook_for_event(settings, event):
            event_hooks = hooks.setdefault(event, [])
            event_hooks.append(HOOK_CONFIG)

    write_settings(settings_path, settings)
    styled_echo("Kingdom workflow hook enabled.", fg=typer.colors.GREEN)
    typer.echo(f"  {settings_path}")


@plugin_app.command("disable", help="Remove the kingdom workflow hook from Claude Code.")
def plugin_disable() -> None:
    """Remove the kingdom hooks from .claude/settings.json."""
    try:
        git_root = find_git_root()
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    settings_path = git_root / ".claude" / "settings.json"
    settings = read_settings(settings_path)

    if not any(has_hook_for_event(settings, event) for event in SUPPORTED_HOOK_EVENTS):
        styled_echo("Kingdom hook is not enabled.", fg=typer.colors.YELLOW)
        return

    for event in SUPPORTED_HOOK_EVENTS:
        event_hooks = settings.get("hooks", {}).get(event, [])
        filtered = [
            matcher
            for matcher in event_hooks
            if not any(h.get("command") == HOOK_COMMAND for h in matcher.get("hooks", []))
        ]

        if filtered:
            settings["hooks"][event] = filtered
        elif event in settings.get("hooks", {}):
            del settings["hooks"][event]

    # Clean up empty hooks dict
    if "hooks" in settings and not settings["hooks"]:
        del settings["hooks"]

    write_settings(settings_path, settings)
    styled_echo("Kingdom workflow hook disabled.", fg=typer.colors.GREEN)


@plugin_app.command("status", help="Check whether a Kingdom host integration is configured.")
def plugin_status(
    host: Annotated[PluginHost, typer.Option("--host", help="Agent host to inspect.")] = PluginHost.CLAUDE,
) -> None:
    """Show whether the kingdom hook is currently enabled."""
    if host is PluginHost.CODEX:
        if is_codex_plugin_configured(Path.home()):
            styled_echo("Kingdom Codex plugin: configured", fg=typer.colors.GREEN)
        else:
            styled_echo("Kingdom Codex plugin: not configured", fg=typer.colors.YELLOW)
        return

    try:
        git_root = find_git_root()
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    settings_path = git_root / ".claude" / "settings.json"
    settings = read_settings(settings_path)

    if has_full_hook_installation(settings):
        styled_echo("Kingdom hook: enabled", fg=typer.colors.GREEN)
    elif is_hook_installed(settings):
        styled_echo("Kingdom hook: enabled (legacy lifecycle coverage)", fg=typer.colors.GREEN)
    else:
        styled_echo("Kingdom hook: disabled", fg=typer.colors.YELLOW)
