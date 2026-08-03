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
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


def find_project_root(cwd: Path | None = None) -> Path:
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
    cwd = cwd or Path.cwd()

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


def runtime_root(base: Path) -> Path:
    return state_root(base) / "runtime"


def terminal_context_root(base: Path) -> Path:
    return runtime_root(base) / "terminal-context"


def execution_context_root(base: Path) -> Path:
    return runtime_root(base) / "contexts"


@dataclass(frozen=True)
class ExecutionContext:
    context_id: str
    host: str
    role: str
    session_id: str
    parent_agent_id: str | None
    agent_type: str | None
    cwd: str
    last_seen: datetime
    source: str


TERMINAL_CONTEXT_ENV_VARS = (
    "KD_TERMINAL_ID",
    "TMUX_PANE",
    "STY",
    "WEZTERM_PANE",
    "TERM_SESSION_ID",
    "ITERM_SESSION_ID",
    "KITTY_WINDOW_ID",
    "WT_SESSION",
    "TTY",
    "SSH_TTY",
)

MAX_CONTEXT_IDENTIFIER_LENGTH = 256
DEFAULT_CONTEXT_STALE_AFTER = timedelta(hours=24)


def validate_context_identifier(name: str, value: str) -> str:
    identifier = value.strip()
    if not identifier:
        raise ValueError(f"{name} must not be empty")
    if len(identifier) > MAX_CONTEXT_IDENTIFIER_LENGTH:
        raise ValueError(f"{name} must be at most {MAX_CONTEXT_IDENTIFIER_LENGTH} characters")
    if any(character in identifier for character in ("\n", "\r", "\0")):
        raise ValueError(f"{name} must be a single-line identifier")
    return identifier


def normalize_context_host(host: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", host.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("context host must contain a letter or number")
    return normalized


def compact_context_id(context_id: str, digest_length: int = 8) -> str:
    host, separator, digest = context_id.partition(":")
    if not separator or len(digest) <= digest_length or not re.fullmatch(r"[0-9a-f]+", digest):
        return context_id
    return f"{host}:{digest[:digest_length]}"


def terminal_fallback_identity() -> tuple[str, str] | None:
    for name in TERMINAL_CONTEXT_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return name, validate_context_identifier(name, value)

    for fd in (0, 1, 2):
        try:
            return "TTY", validate_context_identifier("TTY", os.ttyname(fd))
        except OSError:
            pass
    return None


def resolve_execution_context(
    *,
    session_id: str | None = None,
    host: str | None = None,
    role: str | None = None,
    parent_agent_id: str | None = None,
    agent_type: str | None = None,
    cwd: Path | None = None,
    now: datetime | None = None,
) -> ExecutionContext | None:
    explicit_context = os.environ.get("KD_CONTEXT")
    codex_thread = os.environ.get("CODEX_THREAD_ID")

    if explicit_context:
        stable_id = validate_context_identifier("KD_CONTEXT", explicit_context)
        source = "KD_CONTEXT"
        resolved_host = host or os.environ.get("KD_HOST") or "kingdom"
    elif session_id:
        stable_id = validate_context_identifier("session_id", session_id)
        source = "hook"
        resolved_host = host or os.environ.get("KD_HOST") or "hook"
    elif codex_thread:
        stable_id = validate_context_identifier("CODEX_THREAD_ID", codex_thread)
        source = "CODEX_THREAD_ID"
        resolved_host = host or "codex"
    else:
        terminal_identity = terminal_fallback_identity()
        if terminal_identity is None:
            return None
        terminal_source, terminal_id = terminal_identity
        stable_id = f"{terminal_source}:{terminal_id}"
        source = terminal_source
        resolved_host = host or "terminal"

    normalized_host = normalize_context_host(resolved_host)
    resolved_role = normalize_context_host(
        role or os.environ.get("KD_ROLE") or ("subagent" if parent_agent_id else "agent")
    )
    digest = hashlib.sha256(f"{normalized_host}\0{stable_id}".encode()).hexdigest()[:16]
    validated_parent = (
        validate_context_identifier("parent_agent_id", parent_agent_id) if parent_agent_id is not None else None
    )
    return ExecutionContext(
        context_id=f"{normalized_host}:{digest}",
        host=normalized_host,
        role=resolved_role,
        session_id=stable_id,
        parent_agent_id=validated_parent,
        agent_type=normalize_context_host(agent_type) if agent_type else None,
        cwd=str((cwd or Path.cwd()).resolve()),
        last_seen=now or datetime.now(UTC),
        source=source,
    )


def execution_context_path(base: Path, context: ExecutionContext) -> Path:
    digest = context.context_id.split(":", 1)[-1]
    return execution_context_root(base) / f"{context.host}-{digest}.json"


def record_execution_ticket_context(
    base: Path,
    context: ExecutionContext,
    ticket_id: str,
    *,
    feature: str,
    location: str | None = None,
) -> None:
    path = execution_context_path(base, context)
    ensure_dir(path.parent)
    write_json(
        path,
        {
            "schema_version": 1,
            "context_id": context.context_id,
            "host": context.host,
            "role": context.role,
            "session_id": context.session_id,
            "parent_agent_id": context.parent_agent_id,
            "agent_type": context.agent_type,
            "cwd": context.cwd,
            "source": context.source,
            "ticket_id": ticket_id,
            "feature": normalize_branch_name(feature),
            "location": location or f"branch:{normalize_branch_name(feature)}",
            "last_seen": context.last_seen.isoformat(),
            "active": True,
        },
    )


def finish_execution_context(
    base: Path,
    context: ExecutionContext,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    path = execution_context_path(base, context)
    if not path.exists():
        return None

    timestamp = (now or datetime.now(UTC)).isoformat()

    def finish(data: dict[str, Any]) -> dict[str, Any]:
        if data.get("context_id") != context.context_id:
            return data
        data["active"] = False
        data["completed_at"] = timestamp
        data["last_seen"] = timestamp
        return data

    return locked_json_update(path, finish)


def read_execution_ticket_context(base: Path, context: ExecutionContext) -> dict[str, Any] | None:
    try:
        data = read_json(execution_context_path(base, context))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if data.get("context_id") != context.context_id:
        return None
    ticket_id = data.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id:
        return None
    return data


def refresh_execution_context_activity(
    base: Path,
    context: ExecutionContext,
    ticket_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Refresh an active context only when it is still bound to *ticket_id*."""
    path = execution_context_path(base, context)
    if not path.exists():
        return False

    lock_path = path.parent / f".{path.name}.lock"
    with flock(lock_path):
        try:
            data = read_json(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False
        if (
            data.get("context_id") != context.context_id
            or data.get("ticket_id") != ticket_id
            or data.get("active") is False
        ):
            return False
        data["last_seen"] = (now or datetime.now(UTC)).isoformat()
        write_json(path, data)
    return True


def clear_ticket_execution_contexts(
    base: Path,
    ticket_id: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    contexts_root = execution_context_root(base)
    if not contexts_root.exists():
        return []

    timestamp = (now or datetime.now(UTC)).isoformat()
    cleared = []
    for path in sorted(contexts_root.glob("*.json")):
        lock_path = path.parent / f".{path.name}.lock"
        with flock(lock_path):
            try:
                data = read_json(path)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
            if data.get("ticket_id") != ticket_id:
                continue
            data["ticket_id"] = None
            data["last_seen"] = timestamp
            data["unbound_at"] = timestamp
            write_json(path, data)
            context_id = data.get("context_id")
            if isinstance(context_id, str):
                cleared.append(context_id)
    return cleared


def parse_context_last_seen(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp


def list_execution_contexts(
    base: Path,
    *,
    feature: str | None = None,
    stale_after: timedelta = DEFAULT_CONTEXT_STALE_AFTER,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    contexts_root = execution_context_root(base)
    if not contexts_root.exists():
        return []

    current_time = now or datetime.now(UTC)
    normalized_feature = normalize_branch_name(feature) if feature else None
    records: list[tuple[datetime, dict[str, Any]]] = []
    for path in contexts_root.glob("*.json"):
        try:
            data = read_json(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if normalized_feature and data.get("feature") != normalized_feature:
            continue
        if not isinstance(data.get("context_id"), str) or not isinstance(data.get("host"), str):
            continue
        last_seen = parse_context_last_seen(data.get("last_seen"))
        if last_seen is None:
            continue
        record = dict(data)
        record["role"] = data.get("role") if isinstance(data.get("role"), str) else "agent"
        record["active"] = data.get("active") is not False
        record["stale"] = current_time - last_seen > stale_after
        records.append((last_seen, record))

    records.sort(key=lambda item: item[0], reverse=True)
    return [record for _, record in records]


def prune_stale_execution_contexts(
    base: Path,
    *,
    feature: str | None = None,
    stale_after: timedelta = DEFAULT_CONTEXT_STALE_AFTER,
    now: datetime | None = None,
) -> list[str]:
    stale_contexts = [
        context
        for context in list_execution_contexts(base, feature=feature, stale_after=stale_after, now=now)
        if context["stale"]
    ]
    stale_ids = {context["context_id"] for context in stale_contexts}
    if not stale_ids:
        return []

    removed = []
    for path in execution_context_root(base).glob("*.json"):
        try:
            data = read_json(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        context_id = data.get("context_id")
        if context_id not in stale_ids:
            continue
        path.unlink(missing_ok=True)
        (path.parent / f".{path.name}.lock").unlink(missing_ok=True)
        removed.append(context_id)

    stale_legacy_bindings = {
        (context.get("ticket_id"), context.get("feature"))
        for context in stale_contexts
        if context.get("ticket_id") and context.get("feature")
    }
    for path in terminal_context_root(base).glob("*.json"):
        try:
            data = read_json(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if (data.get("ticket_id"), data.get("feature")) not in stale_legacy_bindings:
            continue
        path.unlink(missing_ok=True)
        (path.parent / f".{path.name}.lock").unlink(missing_ok=True)
    return sorted(removed)


def execution_context_is_stale(
    context: ExecutionContext,
    *,
    stale_after: timedelta,
    now: datetime | None = None,
) -> bool:
    return (now or datetime.now(UTC)) - context.last_seen > stale_after


def terminal_context_identity(session_id: str | None = None) -> str | None:
    terminal_identity = terminal_fallback_identity()
    if terminal_identity:
        source, value = terminal_identity
        prefix = "tty" if source == "TTY" else source
        return f"{prefix}:{value}"

    if session_id:
        return f"session:{session_id}"
    return None


def terminal_context_path(base: Path, session_id: str | None = None) -> Path | None:
    identity = terminal_context_identity(session_id)
    if identity is None:
        return None
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return terminal_context_root(base) / f"{key}.json"


def record_terminal_ticket_context(
    base: Path,
    ticket_id: str,
    *,
    feature: str,
    location: str | None = None,
    session_id: str | None = None,
) -> None:
    path = terminal_context_path(base, session_id)
    if path is None:
        return
    ensure_dir(path.parent)
    write_json(
        path,
        {
            "ticket_id": ticket_id,
            "feature": normalize_branch_name(feature),
            "location": location or f"branch:{normalize_branch_name(feature)}",
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def read_terminal_ticket_context(base: Path, session_id: str | None = None) -> dict[str, Any] | None:
    path = terminal_context_path(base, session_id)
    if path is None:
        return None
    try:
        data = read_json(path)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    ticket_id = data.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id:
        return None
    return data


def clear_terminal_ticket_contexts(
    base: Path,
    ticket_id: str,
    *,
    now: datetime | None = None,
) -> int:
    contexts_root = terminal_context_root(base)
    if not contexts_root.exists():
        return 0

    timestamp = (now or datetime.now(UTC)).isoformat()
    cleared = 0
    for path in sorted(contexts_root.glob("*.json")):
        lock_path = path.parent / f".{path.name}.lock"
        with flock(lock_path):
            try:
                data = read_json(path)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                continue
            if data.get("ticket_id") != ticket_id:
                continue
            data["ticket_id"] = None
            data["updated_at"] = timestamp
            data["unbound_at"] = timestamp
            write_json(path, data)
            cleared += 1
    return cleared


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
def flock(lock_path: Path, *, timeout_seconds: float | None = None) -> Iterator[None]:
    """Hold an exclusive advisory lock, optionally failing after a timeout."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fp = open(lock_path, "a+b")  # noqa: SIM115
    acquired = False
    try:
        if timeout_seconds is None:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
            acquired = True
        else:
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"Timed out waiting for lock: {lock_path}") from None
                    time.sleep(min(0.05, remaining))
        yield
    finally:
        if acquired:
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
*.json.lock
.*.lock
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

    return branch_dir


def set_current_run(base: Path, feature: str) -> None:
    """Set the repository's fallback branch without binding an execution context."""
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

    The invocation branch intentionally wins over ``.kd/current`` so long-lived
    sibling worktrees and execution contexts can share one ``.kd/`` directory
    without inheriting one process's workspace default.
    """
    current_path = state_root(base) / "current"

    # 1. Prefer the branch of the worktree where kd was invoked. A shared
    # .kd/current should not force every worktree or execution context onto one branch.
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
