"""State layout helpers for Kingdom runs.

Example:
    from pathlib import Path
    from kingdom.state import ensure_run_layout, set_current_run, resolve_current_run

    root = Path(".")
    ensure_run_layout(root, "example")
    set_current_run(root, "example")
    resolve_current_run(root)
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def normalize_branch_name(branch: str) -> str:
    """Normalize a branch name for use as a directory name.

    Converts slashes to dashes, lowercases, removes non-ASCII characters,
    and collapses multiple dashes into single dashes.

    Examples:
        - 'feature/oauth-refresh' -> 'feature-oauth-refresh'
        - 'JRB/Fix-Bug' -> 'jrb-fix-bug'
        - 'my--branch' -> 'my-branch'
    """
    normalized = unicodedata.normalize("NFKD", branch)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowercased = ascii_only.lower()
    with_dashes = lowercased.replace("/", "-")
    cleaned = re.sub(r"[^a-z0-9-]", "-", with_dashes)
    no_double_dashes = re.sub(r"-+", "-", cleaned)
    result = no_double_dashes.strip("-")
    if not result:
        raise ValueError(f"Branch name normalizes to empty string: {branch!r}")
    return result


def branches_root(base: Path) -> Path:
    return state_root(base) / "branches"


def branch_root(base: Path, branch: str) -> Path:
    return branches_root(base) / normalize_branch_name(branch)


def backlog_root(base: Path) -> Path:
    return state_root(base) / "backlog"


def archive_root(base: Path) -> Path:
    return state_root(base) / "archive"


def state_root(base: Path) -> Path:
    return base / ".kd"


def runs_root(base: Path) -> Path:
    """DEPRECATED: Use branches_root() instead."""
    return state_root(base) / "runs"


def worktrees_root(base: Path) -> Path:
    return state_root(base) / "worktrees"


def run_root(base: Path, feature: str) -> Path:
    """DEPRECATED: Use branch_root() instead."""
    return runs_root(base) / feature


def logs_root(base: Path, feature: str) -> Path:
    """Path to logs directory, preferring branch structure."""
    branch_dir = branch_root(base, feature)
    if branch_dir.exists():
        return branch_dir / "logs"
    return run_root(base, feature) / "logs"


def sessions_root(base: Path, feature: str) -> Path:
    """Path to sessions directory, preferring branch structure."""
    branch_dir = branch_root(base, feature)
    if branch_dir.exists():
        return branch_dir / "sessions"
    return run_root(base, feature) / "sessions"


def tickets_root(base: Path, feature: str) -> Path:
    """Path to tickets directory, preferring branch structure."""
    branch_dir = branch_root(base, feature)
    if branch_dir.exists():
        return branch_dir / "tickets"
    return run_root(base, feature) / "tickets"


def threads_root(base: Path, feature: str) -> Path:
    """Path to threads directory under branch structure."""
    return branch_root(base, feature) / "threads"


def council_logs_root(base: Path, feature: str) -> Path:
    """Path to council run bundles, preferring branch structure."""
    return logs_root(base, feature) / "council"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return {}
    return json.loads(content)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write *data* as JSON to *path*.

    Writes to a uniquely-named temporary file in the same directory, then
    renames into place so concurrent readers never see a partial write and
    concurrent writers don't clobber each other's temp files.
    """
    serialized = json.dumps(data, indent=2, sort_keys=True)
    # Build a unique temp name using pid + thread id to avoid collisions
    # without relying on tempfile.mkstemp (which uses os.open internally
    # and can break under test mocks that patch os.open).
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(f"{serialized}\n", encoding="utf-8")
    os.rename(tmp, path)


@contextmanager
def flock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on *lock_path* for the duration of the block."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(lock_path, "a+b")  # noqa: SIM115
    try:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        fp.close()


def locked_json_update(
    path: Path,
    updater: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Atomic read-modify-write of a JSON file under an advisory file lock.

    Acquires an exclusive ``fcntl.flock`` on ``<path>.lock``, reads the current
    JSON (or ``{}`` if missing), passes it to *updater(data)*, and writes the
    result back via :func:`write_json`.  Returns the updated dict.
    """
    lock_path = path.parent / f".{path.name}.lock"
    with flock(lock_path):
        try:
            data = read_json(path)
        except FileNotFoundError:
            data = {}
        data = updater(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, data)
    return data


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    serialized = json.dumps(record, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{serialized}\n")


def ensure_base_layout(base: Path, create_gitignore: bool = True) -> dict[str, Path]:
    """Create base .kd/ structure. Idempotent.

    Creates both old structure (runs/) and new structure (branches/, backlog/, archive/).
    """
    ensure_dir(state_root(base))
    # Old structure (kept for backwards compatibility)
    ensure_dir(runs_root(base))
    ensure_dir(worktrees_root(base))
    # New branch-centric structure
    ensure_dir(branches_root(base))
    ensure_dir(backlog_root(base))
    ensure_dir(backlog_root(base) / "tickets")
    ensure_dir(archive_root(base))

    gitignore_path = state_root(base) / ".gitignore"
    if create_gitignore and not gitignore_path.exists():
        gitignore_content = """# Operational state (not tracked)
*.json
*.jsonl
*.log
*.session
**/logs/
**/sessions/
worktrees/
current

# Config file is tracked
!config.json
"""
        gitignore_path.write_text(gitignore_content, encoding="utf-8")

    init_worktree_path = state_root(base) / "init-worktree.sh"
    if not init_worktree_path.exists():
        init_worktree_path.write_text(
            "#!/usr/bin/env bash\n"
            '# Kingdom worktree init — runs after "kd peasant start" creates a worktree.\n'
            "# The worktree path is passed as $1.\n"
            "#\n"
            "# Examples:\n"
            '#   cd "$1" && uv sync && pre-commit install\n'
            '#   cd "$1" && npm install\n'
            "#\n"
            'echo "⚔️  Preparing the realm at $1"\n',
            encoding="utf-8",
        )
        init_worktree_path.chmod(0o755)

    return {
        "state_root": state_root(base),
        "runs_root": runs_root(base),
        "worktrees_root": worktrees_root(base),
        "branches_root": branches_root(base),
        "backlog_root": backlog_root(base),
        "archive_root": archive_root(base),
        "gitignore": gitignore_path if create_gitignore else None,
    }


def ensure_branch_layout(base: Path, branch: str) -> Path:
    """Create branch-specific structure under .kd/branches/<normalized-branch>/. Idempotent.

    Creates:
        - .kd/branches/<normalized-branch>/design.md (empty file)
        - .kd/branches/<normalized-branch>/breakdown.md (empty file)
        - .kd/branches/<normalized-branch>/tickets/
        - .kd/branches/<normalized-branch>/logs/
        - .kd/branches/<normalized-branch>/sessions/
        - .kd/branches/<normalized-branch>/state.json (empty {} if not exists)

    Args:
        base: The project root directory.
        branch: The branch name (will be normalized).

    Returns:
        Path to the branch directory (.kd/branches/<normalized-branch>/).
    """
    # Ensure base layout exists first
    ensure_base_layout(base)

    branch_dir = branch_root(base, branch)
    ensure_dir(branch_dir)

    # Create subdirectories
    ensure_dir(branch_dir / "tickets")
    ensure_dir(branch_dir / "logs")
    ensure_dir(branch_dir / "sessions")

    # Create state.json if not exists
    state_path = branch_dir / "state.json"
    if not state_path.exists():
        write_json(state_path, {})

    # Create markdown files if not exist (touch)
    design_path = branch_dir / "design.md"
    if not design_path.exists():
        design_path.write_text("", encoding="utf-8")

    breakdown_path = branch_dir / "breakdown.md"
    if not breakdown_path.exists():
        breakdown_path.write_text("", encoding="utf-8")

    return branch_dir


def ensure_run_layout(base: Path, feature: str) -> dict[str, Path]:
    """DEPRECATED: Use ensure_branch_layout() instead.

    Create run-specific structure under .kd/runs/<feature>/. Idempotent.
    """
    # Ensure base layout exists first
    base_paths = ensure_base_layout(base)

    run_dir = run_root(base, feature)
    ensure_dir(run_dir)
    ensure_dir(logs_root(base, feature))
    ensure_dir(council_logs_root(base, feature))
    ensure_dir(sessions_root(base, feature))
    ensure_dir(tickets_root(base, feature))

    state_path = run_dir / "state.json"
    if not state_path.exists():
        write_json(state_path, {})

    design_path = run_dir / "design.md"
    if not design_path.exists():
        design_path.write_text("", encoding="utf-8")

    breakdown_path = run_dir / "breakdown.md"
    if not breakdown_path.exists():
        breakdown_path.write_text("", encoding="utf-8")

    learnings_path = run_dir / "learnings.md"
    if not learnings_path.exists():
        learnings_path.write_text("", encoding="utf-8")

    return {
        "state_root": base_paths["state_root"],
        "run_root": run_dir,
        "logs_root": logs_root(base, feature),
        "council_logs_root": council_logs_root(base, feature),
        "sessions_root": sessions_root(base, feature),
        "tickets_root": tickets_root(base, feature),
        "state_json": state_path,
        "design_md": design_path,
        "breakdown_md": breakdown_path,
        "learnings_md": learnings_path,
    }


def set_current_run(base: Path, feature: str) -> None:
    ensure_dir(state_root(base))
    current_path = state_root(base) / "current"
    current_path.write_text(f"{feature}\n", encoding="utf-8")


def clear_current_run(base: Path) -> None:
    """Remove the current run pointer."""
    current_path = state_root(base) / "current"
    if current_path.exists():
        current_path.unlink()


def resolve_current_run(base: Path) -> str:
    """Resolve the current active run/branch.

    First checks for branch-based structure (.kd/branches/), then falls back
    to legacy run structure (.kd/runs/) for backwards compatibility.
    """
    current_path = state_root(base) / "current"
    if not current_path.exists():
        raise RuntimeError("No active session. Use `kd start <feature>` first.")

    feature = current_path.read_text(encoding="utf-8").strip()
    if not feature:
        raise RuntimeError("Current session is empty. Use `kd start <feature>` again.")

    # Check new branch-based structure first
    branch_dir = branch_root(base, feature)
    if branch_dir.exists():
        return feature

    # Fall back to legacy runs structure
    legacy_run_dir = run_root(base, feature)
    if legacy_run_dir.exists():
        return feature

    raise RuntimeError(f"Current session '{feature}' not found at {branch_dir} or {legacy_run_dir}.")
