"""Thread model for agent conversations.

Threads are named conversations between agents. Council discussions,
peasant work sessions, and direct messages are all threads.

A thread is a directory under `.kd/branches/<branch>/threads/<thread-id>/`
containing:
  - thread.json   — metadata (members, pattern, created_at) [gitignored]
  - 0001-king.md  — sequential message files [tracked]
  - 0002-claude.md

Message files use YAML frontmatter + markdown body:
    ---
    from: king
    to: all
    timestamp: 2026-02-07T15:30:12Z
    refs:
      - path/to/file.py
    ---

    Message body here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from kingdom.parsing import parse_frontmatter, serialize_yaml_value
from kingdom.state import branch_root, ensure_dir, normalize_branch_name, read_json, write_json

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A single message in a thread."""

    from_: str
    to: str
    body: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    refs: list[str] = field(default_factory=list)
    sequence: int = 0  # set on read


@dataclass
class ThreadMeta:
    """Metadata for a thread (stored in thread.json)."""

    id: str
    members: list[str]
    pattern: str  # council, work, direct
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def threads_root(base: Path, branch: str) -> Path:
    """Return path to .kd/branches/<branch>/threads/."""
    return branch_root(base, branch) / "threads"


def thread_dir(base: Path, branch: str, thread_id: str) -> Path:
    """Return path to a specific thread directory."""
    normalized = normalize_branch_name(thread_id)
    return threads_root(base, branch) / normalized


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def create_thread(
    base: Path,
    branch: str,
    thread_id: str,
    members: list[str],
    pattern: str,
) -> ThreadMeta:
    """Create a new thread directory with metadata.

    Args:
        base: Project root.
        branch: Branch name.
        thread_id: Human-readable thread slug (will be normalized).
        members: List of agent names participating.
        pattern: Thread pattern (council, work, direct).

    Returns:
        ThreadMeta for the created thread.

    Raises:
        FileExistsError: If the thread directory already exists.
    """
    normalized = normalize_branch_name(thread_id)
    tdir = thread_dir(base, branch, normalized)

    if tdir.exists():
        raise FileExistsError(f"Thread already exists: {normalized}")

    ensure_dir(tdir)

    now = datetime.now(UTC)
    meta = ThreadMeta(
        id=normalized,
        members=members,
        pattern=pattern,
        created_at=now,
    )

    meta_path = tdir / "thread.json"
    write_json(
        meta_path,
        {
            "id": normalized,
            "members": members,
            "pattern": pattern,
            "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )

    return meta


def read_thread_meta(tdir: Path) -> ThreadMeta:
    """Read thread.json from a thread directory."""
    meta_path = tdir / "thread.json"
    data = read_json(meta_path)

    created_str = data.get("created_at", "")
    if isinstance(created_str, str) and created_str:
        if created_str.endswith("Z"):
            created_str = created_str[:-1] + "+00:00"
        created_at = datetime.fromisoformat(created_str)
    else:
        created_at = datetime.now(UTC)

    return ThreadMeta(
        id=data["id"],
        members=data.get("members", []),
        pattern=data.get("pattern", "direct"),
        created_at=created_at,
    )


def get_thread(base: Path, branch: str, thread_id: str) -> ThreadMeta:
    """Load metadata for an existing thread.

    Args:
        base: Project root.
        branch: Branch name.
        thread_id: Thread ID (normalized or raw).

    Returns:
        ThreadMeta instance.

    Raises:
        FileNotFoundError: If thread doesn't exist.
    """
    tdir = thread_dir(base, branch, thread_id)
    if not tdir.exists():
        raise FileNotFoundError(f"Thread not found: {normalize_branch_name(thread_id)}")
    return read_thread_meta(tdir)


def list_threads(base: Path, branch: str) -> list[ThreadMeta]:
    """List all threads for a branch, sorted by created_at ascending.

    Args:
        base: Project root.
        branch: Branch name.

    Returns:
        List of ThreadMeta, oldest first.
    """
    troot = threads_root(base, branch)
    if not troot.exists():
        return []

    threads: list[ThreadMeta] = []
    for entry in sorted(troot.iterdir()):
        if entry.is_dir():
            meta_path = entry / "thread.json"
            if meta_path.exists():
                try:
                    threads.append(read_thread_meta(entry))
                except (KeyError, FileNotFoundError):
                    continue

    threads.sort(key=lambda t: t.created_at)
    return threads


def next_message_number(tdir: Path) -> int:
    """Return the next sequential message number for a thread directory.

    Scans existing NNNN-*.md files and returns max + 1, or 1 if empty.
    """
    existing = sorted(tdir.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not existing:
        return 1
    # Parse the number from the last file
    last_name = existing[-1].stem  # e.g. "0003-claude"
    try:
        return int(last_name.split("-", 1)[0]) + 1
    except (ValueError, IndexError):
        return len(existing) + 1


def add_message(
    base: Path,
    branch: str,
    thread_id: str,
    from_: str,
    to: str,
    body: str,
    refs: list[str] | None = None,
) -> Message:
    """Write the next sequential message file to a thread.

    Args:
        base: Project root.
        branch: Branch name.
        thread_id: Thread ID.
        from_: Sender name.
        to: Recipient name (or "all").
        body: Markdown message body.
        refs: Optional list of file path references.

    Returns:
        Message instance with sequence number set.

    Raises:
        FileNotFoundError: If the thread doesn't exist.
    """
    tdir = thread_dir(base, branch, thread_id)
    if not tdir.exists():
        raise FileNotFoundError(f"Thread not found: {normalize_branch_name(thread_id)}")

    refs = refs or []
    seq = next_message_number(tdir)
    now = datetime.now(UTC)

    # Strip trailing whitespace from each line to satisfy pre-commit hooks
    body = "\n".join(line.rstrip() for line in body.splitlines())

    msg = Message(
        from_=from_,
        to=to,
        body=body,
        timestamp=now,
        refs=refs,
        sequence=seq,
    )

    # Build frontmatter
    lines = ["---"]
    lines.append(f"from: {from_}")
    lines.append(f"to: {to}")
    lines.append(f"timestamp: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    if refs:
        lines.append(f"refs: {serialize_yaml_value(refs)}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    lines.append("")

    # Sanitize sender name for filename — use exclusive create ('x') to avoid race
    safe_from = normalize_branch_name(from_)
    content = "\n".join(lines)
    max_retries = 10
    for _ in range(max_retries):
        filename = f"{seq:04d}-{safe_from}.md"
        msg_path = tdir / filename
        try:
            with open(msg_path, "x", encoding="utf-8") as f:
                f.write(content)
        except FileExistsError:
            seq += 1
            msg.sequence = seq
            continue
        break
    else:
        raise RuntimeError(f"Failed to write message after {max_retries} retries")

    return msg


def parse_message(path: Path) -> Message:
    """Parse a message file (YAML frontmatter + markdown body)."""
    content = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    # Parse timestamp
    ts_str = fm.get("timestamp", "")
    if isinstance(ts_str, str) and ts_str:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(ts_str)
    else:
        timestamp = datetime.now(UTC)

    # Parse sequence from filename
    stem = path.stem  # e.g. "0001-king"
    try:
        seq = int(stem.split("-", 1)[0])
    except (ValueError, IndexError):
        seq = 0

    refs = fm.get("refs", [])

    return Message(
        from_=str(fm.get("from", "")),
        to=str(fm.get("to", "")),
        body=body,
        timestamp=timestamp,
        refs=refs if isinstance(refs, list) else [],
        sequence=seq,
    )


# Member state constants for ThreadStatus
MEMBER_RESPONDED = "responded"
MEMBER_RUNNING = "running"
MEMBER_ERRORED = "errored"
MEMBER_TIMED_OUT = "timed_out"
MEMBER_PENDING = "pending"


def is_error_response(body: str) -> bool:
    """Check if a thread message body represents an error response.

    Matches the markers produced by AgentResponse.thread_body().
    """
    return body.startswith("*Error:") or body.startswith("*Empty response")


def is_timeout_response(body: str) -> bool:
    """Check if a thread message body represents a timeout error."""
    return body.startswith("*Error: Timeout")


@dataclass
class MemberState:
    """Rich status for a single member in a thread round."""

    state: str  # One of the MEMBER_* constants
    error: str | None = None  # Error detail for errored/timed_out states


@dataclass
class ThreadStatus:
    """Response status for the most recent round in a thread."""

    thread_id: str
    expected: set[str]
    responded: set[str]
    pending: set[str]
    member_states: dict[str, MemberState] = field(default_factory=dict)


def thread_response_status(base: Path, branch: str, thread_id: str) -> ThreadStatus:
    """Compute per-member status for the most recent king ask in a thread.

    States derived from concrete runtime signals:
      - responded: message exists with no error marker
      - errored: message exists with ``*Error:`` marker (non-timeout)
      - timed_out: message exists with ``*Error: Timeout`` marker
      - running: no message yet but ``.stream-{member}.jsonl`` file exists
      - pending: no message and no stream file

    Only considers responses after the latest king message.
    """
    meta = get_thread(base, branch, thread_id)
    expected = {m for m in meta.members if m != "king"}
    tdir = thread_dir(base, branch, thread_id)

    messages = list_messages(base, branch, thread_id)

    # Find the most recent king message
    last_ask_seq = 0
    for msg in messages:
        if msg.from_ == "king":
            last_ask_seq = msg.sequence

    # Classify each member's response
    responded: set[str] = set()
    member_states: dict[str, MemberState] = {}

    # First pass: check responses after the last ask
    response_bodies: dict[str, str] = {}
    for msg in messages:
        if msg.sequence > last_ask_seq and msg.from_ in expected:
            responded.add(msg.from_)
            response_bodies[msg.from_] = msg.body

    # Classify each expected member
    for name in expected:
        if name in responded:
            body = response_bodies[name]
            if is_timeout_response(body):
                member_states[name] = MemberState(state=MEMBER_TIMED_OUT, error=body)
            elif is_error_response(body):
                member_states[name] = MemberState(state=MEMBER_ERRORED, error=body)
            else:
                member_states[name] = MemberState(state=MEMBER_RESPONDED)
        elif (tdir / f".stream-{name}.jsonl").exists():
            member_states[name] = MemberState(state=MEMBER_RUNNING)
        else:
            member_states[name] = MemberState(state=MEMBER_PENDING)

    return ThreadStatus(
        thread_id=thread_id,
        expected=expected,
        responded=responded,
        pending=expected - responded,
        member_states=member_states,
    )


def list_messages(base: Path, branch: str, thread_id: str) -> list[Message]:
    """List all messages in a thread, in sequential order.

    Args:
        base: Project root.
        branch: Branch name.
        thread_id: Thread ID.

    Returns:
        List of Message instances, sorted by sequence number.

    Raises:
        FileNotFoundError: If the thread doesn't exist.
    """
    tdir = thread_dir(base, branch, thread_id)
    if not tdir.exists():
        raise FileNotFoundError(f"Thread not found: {normalize_branch_name(thread_id)}")

    messages: list[Message] = []
    for path in sorted(tdir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        try:
            messages.append(parse_message(path))
        except (ValueError, FileNotFoundError):
            continue

    messages.sort(key=lambda m: m.sequence)
    return messages
