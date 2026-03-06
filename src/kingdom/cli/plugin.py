"""Plugin management CLI commands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer

from .display import print_error, styled_echo

plugin_app = typer.Typer(name="plugin", help="Manage Claude Code hooks plugin.")

HOOK_COMMAND = "kd hook run"

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop")

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
    """Check if the kingdom hooks are present for all events."""
    return all(has_hook_for_event(settings, event) for event in HOOK_EVENTS)


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

    if is_hook_installed(settings):
        styled_echo("Kingdom hook is already enabled.", fg=typer.colors.YELLOW)
        return

    hooks = settings.setdefault("hooks", {})
    for event in HOOK_EVENTS:
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

    if not any(has_hook_for_event(settings, event) for event in HOOK_EVENTS):
        styled_echo("Kingdom hook is not enabled.", fg=typer.colors.YELLOW)
        return

    for event in HOOK_EVENTS:
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


@plugin_app.command("status", help="Check if the kingdom workflow hook is installed.")
def plugin_status() -> None:
    """Show whether the kingdom hook is currently enabled."""
    try:
        git_root = find_git_root()
    except (ValueError, subprocess.TimeoutExpired) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    settings_path = git_root / ".claude" / "settings.json"
    settings = read_settings(settings_path)

    if is_hook_installed(settings):
        styled_echo("Kingdom hook: enabled", fg=typer.colors.GREEN)
    else:
        styled_echo("Kingdom hook: disabled", fg=typer.colors.YELLOW)
