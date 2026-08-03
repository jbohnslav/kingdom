"""Install Kingdom's first-party Codex plugin without replacing user config."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path
from typing import Literal

PLUGIN_NAME = "kingdom"
CODEX_HOOK_EVENTS = (
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "UserPromptSubmit",
    "PostToolUse",
    "Stop",
)

KINGDOM_PLUGIN_ENTRY = {
    "name": PLUGIN_NAME,
    "source": {"source": "local", "path": "./plugins/kingdom"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Developer Tools",
}

InstallStatus = Literal["installed", "updated", "unchanged"]


@dataclass(frozen=True)
class CodexPluginInstallResult:
    """Summary of one idempotent plugin-source installation."""

    status: InstallStatus
    plugin_root: Path
    marketplace_path: Path
    marketplace_name: str
    changed_files: tuple[str, ...]
    marketplace_changed: bool


def package_version() -> str:
    """Return the installed CLI version, with the manifest as a source-tree fallback."""
    try:
        return version("kingdom-cli")
    except PackageNotFoundError:
        manifest = json.loads(
            (files("kingdom.codex_plugin") / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        return str(manifest["version"])


def plugin_payloads() -> dict[str, bytes]:
    """Build the managed plugin files, including a deterministic Codex cachebuster."""
    plugin_package = files("kingdom.codex_plugin")
    skill_package = files("kingdom.skill")
    hooks = (plugin_package / "hooks" / "hooks.json").read_bytes()
    base_manifest = json.loads((plugin_package / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

    payloads = {
        "hooks/hooks.json": hooks,
        "skills/kingdom/SKILL.md": (skill_package / "SKILL.md").read_bytes(),
    }
    for item in (skill_package / "references").iterdir():
        if item.name.endswith(".md"):
            payloads[f"skills/kingdom/references/{item.name}"] = item.read_bytes()

    digest = hashlib.sha256()
    digest.update(json.dumps(base_manifest, sort_keys=True).encode())
    for relative_path, content in sorted(payloads.items()):
        digest.update(relative_path.encode())
        digest.update(b"\0")
        digest.update(content)
    base_manifest["version"] = f"{package_version().split('+', 1)[0]}+codex.{digest.hexdigest()[:12]}"
    payloads[".codex-plugin/plugin.json"] = (json.dumps(base_manifest, indent=2) + "\n").encode()
    return payloads


def write_if_changed(path: Path, content: bytes) -> bool:
    """Write bytes only when their managed content changed."""
    try:
        if path.read_bytes() == content:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.kingdom.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return True


def read_marketplace(path: Path) -> dict:
    """Read a personal marketplace without silently replacing malformed data."""
    if not path.exists():
        return {
            "name": "personal",
            "interface": {"displayName": "Personal"},
            "plugins": [],
        }
    try:
        marketplace = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}") from None
    if not isinstance(marketplace, dict):
        raise ValueError(f"Marketplace root in {path} must be an object")
    name = marketplace.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"Marketplace in {path} must have a non-empty name")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        raise ValueError(f"Marketplace plugins in {path} must be a list")
    interface = marketplace.get("interface")
    if interface is not None and not isinstance(interface, dict):
        raise ValueError(f"Marketplace interface in {path} must be an object")
    return marketplace


def merge_marketplace_entry(marketplace: dict) -> bool:
    """Add or replace only Kingdom's entry, preserving its list position."""
    plugins = marketplace["plugins"]
    for index, entry in enumerate(plugins):
        if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME:
            if entry == KINGDOM_PLUGIN_ENTRY:
                return False
            plugins[index] = KINGDOM_PLUGIN_ENTRY
            return True
    plugins.append(KINGDOM_PLUGIN_ENTRY)
    return True


def install_codex_plugin(home: Path | None = None) -> CodexPluginInstallResult:
    """Install or refresh Kingdom in Codex's default personal marketplace."""
    resolved_home = home or Path.home()
    plugin_root = resolved_home / "plugins" / PLUGIN_NAME
    marketplace_path = resolved_home / ".agents" / "plugins" / "marketplace.json"
    plugin_existed = plugin_root.exists()

    changed_files = []
    for relative_path, content in plugin_payloads().items():
        if write_if_changed(plugin_root / relative_path, content):
            changed_files.append(relative_path)

    marketplace = read_marketplace(marketplace_path)
    marketplace_changed = merge_marketplace_entry(marketplace)
    if marketplace_changed:
        write_if_changed(marketplace_path, (json.dumps(marketplace, indent=2) + "\n").encode())

    if not plugin_existed:
        status: InstallStatus = "installed"
    elif changed_files or marketplace_changed:
        status = "updated"
    else:
        status = "unchanged"
    return CodexPluginInstallResult(
        status=status,
        plugin_root=plugin_root,
        marketplace_path=marketplace_path,
        marketplace_name=marketplace["name"],
        changed_files=tuple(changed_files),
        marketplace_changed=marketplace_changed,
    )


def is_codex_plugin_configured(home: Path | None = None) -> bool:
    """Return whether the managed plugin files and marketplace entry exist."""
    resolved_home = home or Path.home()
    plugin_root = resolved_home / "plugins" / PLUGIN_NAME
    required_files = (
        plugin_root / ".codex-plugin" / "plugin.json",
        plugin_root / "hooks" / "hooks.json",
        plugin_root / "skills" / "kingdom" / "SKILL.md",
    )
    if not all(path.is_file() for path in required_files):
        return False

    try:
        marketplace = read_marketplace(resolved_home / ".agents" / "plugins" / "marketplace.json")
    except ValueError:
        return False
    return any(isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME for entry in marketplace["plugins"])


def codex_plugin_install_detected(home: Path | None = None) -> bool:
    """Return whether an existing install should be repaired during ``kd update``."""
    resolved_home = home or Path.home()
    if (resolved_home / "plugins" / PLUGIN_NAME).exists():
        return True
    try:
        marketplace = read_marketplace(resolved_home / ".agents" / "plugins" / "marketplace.json")
    except ValueError:
        return False
    return any(isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME for entry in marketplace["plugins"])
