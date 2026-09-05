"""Shared CLI helper utilities for the Kingdom CLI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import typer

from kingdom.state import find_project_root
from kingdom.ticket import AmbiguousTicketMatch, Ticket, find_ticket

from .display import print_error

SkillInstallStatus = Literal["refreshed", "skipped", "failed"]
SkillTargetStatus = Literal["installed", "updated", "adopted", "skipped", "manual"]
SKILL_MANIFEST = ".kingdom-managed.json"


@dataclass(frozen=True)
class SkillTarget:
    host: str
    path: Path
    enabled: bool
    note: str = ""


def verbose_echo(message: str) -> None:
    """Print a debug message to stderr when --verbose is set."""
    import click

    ctx = click.get_current_context(silent=True)
    if ctx is None or not ctx.ensure_object(dict).get("verbose"):
        return
    from .display import error_console

    error_console.print(f"[dim]{message}[/dim]")


def resolve_ticket_or_exit(
    base: Path,
    ticket_id: str,
    *,
    not_found_label: str = "Ticket not found",
    branch: str | None = None,
) -> tuple[Ticket, Path]:
    """Find a ticket by ID or exit with a clear error.

    Handles ``AmbiguousTicketMatch`` and not-found cases with consistent
    error messages and exit code 1.
    """
    try:
        result = find_ticket(base, ticket_id, branch=branch)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None
    if result is None:
        print_error(f"{not_found_label}: {ticket_id}")
        raise typer.Exit(code=1)
    return result


def peasant_session_name(ticket_id: str) -> str:
    """Return the canonical session name for a peasant working on *ticket_id*."""
    return f"peasant-{ticket_id}"


def peasant_thread_id(ticket_id: str) -> str:
    """Return the canonical thread ID for a peasant work thread."""
    return f"{ticket_id}-work"


def is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def not_implemented(command: str) -> None:
    print_error(f"{command}: not implemented yet.")
    raise typer.Exit(code=1)


def require_project_root() -> Path:
    """Find the project root or exit with a clear error."""
    try:
        return find_project_root()
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None


def is_git_repo(base: Path) -> bool:
    """Check if base is inside a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=base,
    )
    return result.returncode == 0


def ensure_feature_branch(feature: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to read git branch")

    current = result.stdout.strip()
    if current == feature:
        return

    if current in {"main", "master"}:
        checkout = subprocess.run(["git", "checkout", "-b", feature], text=True)
        if checkout.returncode != 0:
            raise RuntimeError(f"Failed to create branch '{feature}'")
        typer.echo(f"Created branch {feature}")
        return

    typer.echo(f"Warning: current branch '{current}' does not match feature '{feature}'.")


def skill_install_targets(home: Path) -> list[Path]:
    """Return Claude's skill target, plus Cursor/Codex when their config dirs exist."""
    return [target.path for target in skill_targets(home) if target.enabled]


def skill_targets(home: Path) -> list[SkillTarget]:
    """Return every supported host and whether its local config root exists."""
    return [
        SkillTarget("claude", home / ".claude" / "skills" / "kingdom", True),
        SkillTarget(
            "codex",
            home / ".codex" / "skills" / "kingdom",
            (home / ".codex").is_dir(),
            "host config directory not found",
        ),
        SkillTarget(
            "cursor",
            home / ".cursor" / "skills" / "kingdom",
            (home / ".cursor").is_dir(),
            "host config directory not found; Cursor hooks remain a separate limited integration",
        ),
    ]


def skill_home() -> Path:
    """Return an explicit skill target root when the environment isolates one."""
    configured = os.environ.get("KD_SKILL_HOME")
    return Path(configured) if configured else Path.home()


def bundled_skill_files(skill_package: Traversable) -> dict[str, bytes]:
    """Read the packaged skill files keyed by target-relative path."""
    from importlib.resources import as_file

    files: dict[str, bytes] = {}
    with as_file(skill_package / "SKILL.md") as source:
        files["SKILL.md"] = source.read_bytes()
    for item in (skill_package / "references").iterdir():
        if item.name.endswith(".md"):
            with as_file(item) as source:
                files[f"references/{item.name}"] = source.read_bytes()
    return files


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def skill_manifest(files: dict[str, bytes]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "files": {name: content_hash(content) for name, content in sorted(files.items())},
    }


def skill_manifest_path_is_safe(name: str) -> bool:
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    return (
        bool(posix_path.parts)
        and "\0" not in name
        and not posix_path.anchor
        and not windows_path.anchor
        and ".." not in posix_path.parts
        and ".." not in windows_path.parts
    )


def skill_paths_are_safe(target: Path, names: Iterable[str]) -> bool:
    try:
        target_root = target.resolve(strict=False)
        for name in names:
            path = target / name
            resolved_path = path.resolve(strict=False)
            if not resolved_path.is_relative_to(target_root) or path.is_symlink():
                return False
            for parent in path.parents:
                if parent == target:
                    break
                if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                    return False
            else:
                return False
            if path.exists() and not path.is_file():
                return False
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def read_skill_manifest(path: Path) -> dict[str, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if data.get("schema_version") != 1 or not isinstance(files, dict):
        return None
    if not all(isinstance(name, str) and isinstance(digest, str) for name, digest in files.items()):
        return None
    if not all(skill_manifest_path_is_safe(name) for name in files):
        return None
    return files


def file_matches_hash(path: Path, expected: str) -> bool:
    try:
        return content_hash(path.read_bytes()) == expected
    except OSError:
        return False


def target_matches_hashes(target: Path, hashes: dict[str, str]) -> bool:
    return all(file_matches_hash(target / name, expected) for name, expected in hashes.items())


def target_matches_bundle(target: Path, files: dict[str, bytes]) -> bool:
    try:
        return all((target / name).read_bytes() == content for name, content in files.items())
    except OSError:
        return False


def write_skill_bundle(target: Path, files: dict[str, bytes]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest_path = target / SKILL_MANIFEST
    manifest_path.write_text(json.dumps(skill_manifest(files), indent=2) + "\n", encoding="utf-8")


def install_skill_target(target: Path, files: dict[str, bytes]) -> tuple[SkillTargetStatus, str]:
    """Safely install one managed skill target without replacing unknown edits."""
    if target.is_symlink():
        return "skipped", "dev symlink"
    if target.exists() and not target.is_dir():
        return "manual", "target exists and is not a directory"
    if not all(skill_manifest_path_is_safe(name) for name in files) or not skill_paths_are_safe(target, files):
        return "manual", "bundled skill paths are invalid"

    manifest_path = target / SKILL_MANIFEST
    if not skill_paths_are_safe(target, [SKILL_MANIFEST]):
        return "manual", "managed-file manifest is invalid"
    manifest_hashes = read_skill_manifest(manifest_path)
    if manifest_path.exists() and manifest_hashes is None:
        return "manual", "managed-file manifest is invalid"
    if manifest_hashes is not None and not skill_paths_are_safe(target, manifest_hashes):
        return "manual", "managed-file manifest is invalid"

    if manifest_hashes is None:
        conflicts = [
            name
            for name, content in files.items()
            if (target / name).exists() and (target / name).read_bytes() != content
        ]
        if conflicts:
            return "manual", f"unmanaged files differ: {', '.join(conflicts)}"
        existed = target.exists()
        already_current = existed and target_matches_bundle(target, files)
        write_skill_bundle(target, files)
        return ("adopted", "existing files matched") if already_current else ("installed", "new managed install")

    retained_hashes = {name: digest for name, digest in manifest_hashes.items() if name in files}
    if not target_matches_hashes(target, retained_hashes):
        return "manual", "managed files were modified locally"

    untracked_conflicts = [
        name
        for name, content in files.items()
        if name not in manifest_hashes and (target / name).exists() and (target / name).read_bytes() != content
    ]
    if untracked_conflicts:
        return "manual", f"new bundled files conflict: {', '.join(untracked_conflicts)}"

    next_hashes = {name: content_hash(content) for name, content in files.items()}
    if target_matches_bundle(target, files) and manifest_hashes == next_hashes:
        return "skipped", "already current"

    retired_files = [
        target / name
        for name, expected in manifest_hashes.items()
        if name not in files and file_matches_hash(target / name, expected)
    ]
    for retired_file in retired_files:
        retired_file.unlink()

    write_skill_bundle(target, files)
    return "updated", "managed files refreshed"


def install_skill() -> SkillInstallStatus:
    """Install the bundled kingdom skill to supported local agent skill dirs.

    Copies SKILL.md and reference files from the package into Claude, and into
    Cursor/Codex when their top-level config directories already exist. A hash
    manifest allows future refreshes while preserving unknown or modified files.
    Every host gets an explicit updated, skipped, or manual-action result.

    Returns "refreshed" when any target was written, "skipped" when every
    enabled target is current or a symlink, and "failed" on error or conflict.
    """
    from importlib.resources import files

    try:
        targets = skill_targets(skill_home())
        skill_pkg = files("kingdom.skill")
        bundled_files = bundled_skill_files(skill_pkg)
        refreshed_targets = 0
        failed_targets = 0

        for target in targets:
            if not target.enabled:
                typer.echo(f"  {target.host}: skipped — {target.note}")
                continue
            try:
                status, note = install_skill_target(target.path, bundled_files)
            except OSError as exc:
                status, note = "manual", str(exc)
            if status in {"installed", "updated", "adopted"}:
                refreshed_targets += 1
            elif status == "manual":
                failed_targets += 1
            if status == "manual":
                label = "manual action needed"
                note += "; review or move the differing files, then rerun `kd update`"
            elif status in {"installed", "updated", "adopted"}:
                label = "updated"
            else:
                label = "skipped"
            typer.echo(f"  {target.host}: {label} — {target.path} ({note})")
    except (OSError, RuntimeError) as exc:
        typer.echo(f"Warning: could not install skill ({exc})")
        return "failed"

    if failed_targets:
        return "failed"
    if refreshed_targets:
        return "refreshed"
    return "skipped"
