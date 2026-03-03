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
