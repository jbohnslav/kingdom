"""State layout helpers for Kingdom branches.

Example:
    from pathlib import Path
    from kingdom.state import ensure_branch_layout, set_current_run, resolve_current_run

    root = Path(".")
    ensure_branch_layout(root, "example")
    set_current_run(root, "example")
    resolve_current_run(root)
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import threading
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


def find_git_root(cwd: Path | None = None) -> Path | None:
    """Return the current invocation worktree root, or None outside git."""
    cwd = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def parse_worktree_list(output: str) -> list[Path]:
    """Parse ``git worktree list --porcelain`` output into worktree paths."""
    paths: list[Path] = []
    for line in output.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.removeprefix("worktree ")).resolve())
    return paths


def has_git_marker(cwd: Path | None = None) -> bool:
    """Return True when cwd or one of its parents looks like a git checkout."""
    current = cwd or Path.cwd()
    while True:
        if (current / ".git").exists():
            return True
        if current.parent == current:
            return False
        current = current.parent


def find_kd_base_from_git_worktrees(cwd: Path | None = None) -> Path | None:
    """Find a sibling worktree that owns ``.kd/``.

    Manual long-lived worktrees may not have the tracked ``.kd/`` directory
    checked out. Git's worktree registry lets us find the sibling checkout that
    does without moving Kingdom state into a global home directory.
    """
    cwd = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None

    candidates = [path for path in parse_worktree_list(result.stdout) if (path / ".kd").is_dir()]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    primary_candidates = [path for path in candidates if (path / ".git").is_dir()]
    if len(primary_candidates) == 1:
        return primary_candidates[0]

    options = "\n".join(f"  {path}" for path in candidates)
    raise ValueError(f"Multiple git worktrees contain .kd/. Set KD_BASE to choose one explicitly:\n{options}")


def find_project_root() -> Path:
    """Locate the Kingdom project root directory.

    Resolution order:
    1. KD_BASE env var (explicit override for agents/CI)
    2. cwd (if .kd/ exists here, fast path)
    3. Walk parent directories looking for .kd/
    4. git rev-parse --show-toplevel (belt-and-suspenders fallback)
    5. git worktree list --porcelain sibling fallback
    6. Error with clear hint to run kd init

    Raises ValueError with a descriptive message if no root is found, or
    if multiple sibling git worktrees contain .kd/ and KD_BASE is needed
    to choose one explicitly.
    """
    root: Path | None = None
    cwd = Path.cwd()

    # 1. KD_BASE env var — explicit override, fail loudly if invalid
    kd_base = os.environ.get("KD_BASE")
    if kd_base:
        p = Path(kd_base).resolve()
        if not (p / ".kd").is_dir():
            raise ValueError(f"KD_BASE={kd_base} does not contain a .kd/ directory")
        root = p

    # 2. cwd fast path
    if root is None and (cwd / ".kd").is_dir():
        root = cwd.resolve()

    # 3. Walk parent directories
    if root is None:
        for parent in cwd.parents:
            if (parent / ".kd").is_dir():
                root = parent.resolve()
                break

    # 4. git rev-parse fallback
    if root is None:
        git_root = find_git_root(cwd)
        if git_root and (git_root / ".kd").is_dir():
            root = git_root

    # 5. Manual sibling worktree fallback
    if root is None:
        root = find_kd_base_from_git_worktrees(cwd)

    # 6. Error
    if root is None:
        raise ValueError("No .kd/ directory found. Run `kd init` to initialize.")

    check_no_legacy_runs(root)
    return root


def check_no_legacy_runs(base: Path) -> None:
    """Raise if a non-empty legacy .kd/runs/ directory exists.

    The runs/ → branches/ migration is complete. If .kd/runs/ still has content,
    the user must rename it manually before proceeding.
    """
    runs_dir = state_root(base) / "runs"
    if runs_dir.is_dir() and any(runs_dir.iterdir()):
        raise ValueError("Legacy .kd/runs/ directory found. Rename it to .kd/branches/ manually and retry.")


def worktrees_root(base: Path) -> Path:
    return state_root(base) / "worktrees"


def logs_root(base: Path, feature: str) -> Path:
    return branch_root(base, feature) / "logs"


def sessions_root(base: Path, feature: str) -> Path:
    return branch_root(base, feature) / "sessions"


def tickets_root(base: Path, feature: str) -> Path:
    return branch_root(base, feature) / "tickets"


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
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
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
    """Create base .kd/ structure. Idempotent."""
    ensure_dir(state_root(base))
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


def set_current_run(base: Path, feature: str) -> None:
    ensure_dir(state_root(base))
    current_path = state_root(base) / "current"
    current_path.write_text(f"{feature}\n", encoding="utf-8")


def clear_current_run(base: Path) -> None:
    """Remove the current run pointer."""
    current_path = state_root(base) / "current"
    if current_path.exists():
        current_path.unlink()


def get_current_git_branch(cwd: Path | None = None) -> str | None:
    """Get the current git branch name, or None if not in a repo or detached HEAD."""
    cwd = cwd or Path.cwd()
    if not has_git_marker(cwd):
        return None
    try:
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, cwd=cwd)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    if branch == "HEAD":
        return None
    return branch


def resolve_current_run(base: Path) -> str:
    """Resolve the current active run/branch.

    Resolution order:
    1. Current invocation worktree git branch matched against .kd/branches/
    2. Explicit .kd/current file (repo default, set by ``kd start`` / ``kd switch``)
    3. Error with helpful message
    """
    current_path = state_root(base) / "current"

    # 1. Prefer the branch of the worktree where kd was invoked. A shared
    # .kd/current file should not force every human worktree onto one session.
    git_branch = get_current_git_branch()
    if git_branch:
        try:
            normalized = normalize_branch_name(git_branch)
        except ValueError:
            pass
        else:
            branch_dir = branches_root(base) / normalized
            if branch_dir.exists():
                return normalized

    # 2. Explicit current file is a repo-wide default/fallback.
    if current_path.exists():
        feature = current_path.read_text(encoding="utf-8").strip()
        if feature:
            branch_dir = branch_root(base, feature)
            if branch_dir.exists():
                return feature

            # Stale pointer — fall through to the helpful error below.

    raise RuntimeError("No active session. Use `kd start <feature>` or switch to a tracked branch.")
