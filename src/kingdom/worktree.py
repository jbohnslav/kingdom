"""Worktree management for Kingdom peasant agents.

Handles git worktree creation, removal, and state.json bookkeeping.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from kingdom.state import read_json, resolve_current_run, state_root, write_json


def worktree_path_for(base: Path, full_ticket_id: str) -> Path:
    """Return the canonical worktree path for a ticket (may not exist yet)."""
    return state_root(base) / "worktrees" / full_ticket_id


def design_state_path(base: Path, feature: str) -> Path:
    """Return the state.json path for a feature branch."""
    from kingdom.state import branch_root

    return branch_root(base, feature) / "state.json"


def run_init_script(
    base: Path, worktree_path: Path, *, step_prefix: str = "", log: Callable[[str], None] = print
) -> None:
    """Run ``.kd/init-worktree.sh`` if present and executable."""
    init_script = state_root(base) / "init-worktree.sh"
    if init_script.exists() and os.access(init_script, os.X_OK):
        log(f"{step_prefix}Running init-worktree.sh...")
        init_result = subprocess.run(
            [str(init_script), str(worktree_path)],
            capture_output=True,
            text=True,
        )
        if init_result.stdout.strip():
            log(init_result.stdout.strip())
        if init_result.returncode != 0:
            log(f"Warning: init-worktree.sh failed (exit {init_result.returncode})")
            if init_result.stderr.strip():
                log(init_result.stderr.strip())
    elif init_script.exists():
        log(f"{step_prefix}init-worktree.sh exists but is not executable, skipping.")
    else:
        log(f"{step_prefix}No init-worktree.sh found, skipping dependency refresh.")


def sync_workflow_files(base: Path, worktree_path: Path, log: Callable[[str], None] = print) -> None:
    """Copy untracked workflow files from the project root into a worktree.

    Currently syncs ``.claude/settings.json`` — the only critical untracked
    file that worktrees miss (tracked files like CLAUDE.md are already present).
    """
    files_to_sync = [Path(".claude", "settings.json")]

    for rel in files_to_sync:
        src = base / rel
        dst = worktree_path / rel
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            log(f"Synced {rel} into worktree")


def porcelain_paths(line: str) -> list[str]:
    """Return paths from one ``git status --porcelain`` line."""
    if len(line) < 4:
        return []
    payload = line[3:].strip()
    if " -> " in payload:
        return [part.strip() for part in payload.split(" -> ", 1)]
    return [payload]


def is_kd_change(line: str) -> bool:
    """Return True when a porcelain status line only touches .kd files."""
    paths = porcelain_paths(line)
    return bool(paths) and all(path == ".kd" or path.startswith(".kd/") for path in paths)


def check_uncommitted_changes(base: Path, *, ignore_kd: bool = False) -> list[str]:
    """Return list of uncommitted change descriptions, or empty list if clean.

    Set ``ignore_kd`` when ticket/session bookkeeping should not count as
    user code dirtiness.

    Fails open: returns an empty list if git is unavailable or errors out.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=base,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if ignore_kd:
            lines = [line for line in lines if not is_kd_change(line)]
        return lines
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def create_worktree(base: Path, full_ticket_id: str, log: Callable[[str], None] = print) -> Path:
    """Create a git worktree for a ticket. Returns the worktree path."""
    worktree_path = worktree_path_for(base, full_ticket_id)

    if worktree_path.exists():
        return worktree_path

    worktrees_dir = worktree_path.parent
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    branch_name = f"ticket/{full_ticket_id}"

    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True,
        text=True,
        cwd=base,
    )
    branch_exists = result.returncode == 0

    if branch_exists:
        log(f"Creating worktree from existing branch {branch_name}...")
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            capture_output=True,
            text=True,
            cwd=base,
        )
    else:
        log(f"Creating worktree with new branch {branch_name}...")
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
            cwd=base,
        )

    if result.returncode != 0:
        raise RuntimeError(f"Error creating worktree: {result.stderr.strip()}")

    run_init_script(base, worktree_path, log=log)
    sync_workflow_files(base, worktree_path, log=log)

    try:
        feature = resolve_current_run(base)
        state_path = design_state_path(base, feature)
        state = read_json(state_path) if state_path.exists() else {}
        worktrees = state.get("worktrees", {})
        worktrees[full_ticket_id] = str(worktree_path)
        state["worktrees"] = worktrees
        write_json(state_path, state)
    except RuntimeError as exc:
        log(f"Warning: could not record worktree in state.json: {exc}")

    return worktree_path


def remove_worktree(base: Path, full_ticket_id: str, log: Callable[[str], None] = print) -> None:
    """Remove a git worktree for a ticket."""
    worktree_path = worktree_path_for(base, full_ticket_id)

    if not worktree_path.exists():
        raise FileNotFoundError(f"No worktree found for {full_ticket_id}")

    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        capture_output=True,
        text=True,
        cwd=base,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Error removing worktree: {result.stderr.strip()}")

    try:
        feature = resolve_current_run(base)
        state_path = design_state_path(base, feature)
        state = read_json(state_path) if state_path.exists() else {}
        worktrees = state.get("worktrees", {})
        worktrees.pop(full_ticket_id, None)
        state["worktrees"] = worktrees
        write_json(state_path, state)
    except RuntimeError as exc:
        log(f"Warning: could not update state.json worktree map: {exc}")
