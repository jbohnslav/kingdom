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

from kingdom.parsing import parse_frontmatter, parse_iso_datetime, serialize_frontmatter
from kingdom.state import (
    archive_root,
    branch_root,
    branches_root,
    ensure_dir,
    normalize_branch_name,
    read_json,
    write_json,
)


class AmbiguousThreadMatch(Exception):
    """Raised when a partial thread ID matches multiple threads."""

    def __init__(self, partial_id: str, matches: list[ThreadMeta]) -> None:
        self.partial_id = partial_id
        self.matches = matches
        match_ids = [m.id for m in matches]
        super().__init__(f"'{partial_id}' matches multiple threads: {', '.join(match_ids)}")


class ThreadNotFoundError(Exception):
    """Raised when a thread ID does not match any thread, with suggestions."""

    def __init__(self, thread_id: str, available: list[ThreadMeta] | None = None) -> None:
        self.thread_id = thread_id
        self.available = available or []
        super().__init__(f"Thread not found: {thread_id}")


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
    status: str | None = None  # complete, error, timeout, interrupted


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
    return branch_root(base, branch) / "threads"


def thread_dir(base: Path, branch: str, thread_id: str) -> Path:
    normalized = normalize_branch_name(thread_id)
    return threads_root(base, branch) / normalized


# ---------------------------------------------------------------------------
# Cross-branch / archive thread lookup
# ---------------------------------------------------------------------------


@dataclass
class ThreadLocation:
    """A thread with its source branch and archive status."""

    meta: ThreadMeta
    branch: str
    archived: bool


def archive_threads_root(base: Path, branch: str) -> Path:
    return archive_root(base) / normalize_branch_name(branch) / "threads"


def list_all_branch_names(base: Path) -> list[tuple[str, bool]]:
    """Return all branch names with their archive status.

    Returns list of (branch_name, is_archived) tuples.
    """
    result: list[tuple[str, bool]] = []
    broot = branches_root(base)
    if broot.exists():
        for entry in sorted(broot.iterdir()):
            if entry.is_dir():
                result.append((entry.name, False))
    aroot = archive_root(base)
    if aroot.exists():
        for entry in sorted(aroot.iterdir()):
            if entry.is_dir() and entry.name != "backlog":
                result.append((entry.name, True))
    return result


def list_threads_in_dir(troot: Path) -> list[ThreadMeta]:
    """List threads from a threads directory path."""
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
    return threads


def list_all_threads(base: Path, pattern: str | None = None) -> list[ThreadLocation]:
    """List threads across all branches and archive, sorted by created_at."""
    results: list[ThreadLocation] = []
    for branch_name, is_archived in list_all_branch_names(base):
        if is_archived:
            troot = archive_threads_root(base, branch_name)
        else:
            troot = threads_root(base, branch_name)
        for meta in list_threads_in_dir(troot):
            if pattern and meta.pattern != pattern:
                continue
            results.append(ThreadLocation(meta=meta, branch=branch_name, archived=is_archived))
    results.sort(key=lambda loc: loc.meta.created_at)
    return results


def resolve_thread_globally(
    base: Path,
    partial_id: str,
    pattern: str | None = None,
) -> ThreadLocation:
    """Resolve a thread by ID across all branches and archive.

    Tries exact match first, then prefix match. Returns the first unique match.

    Raises:
        ThreadNotFoundError: No thread matches.
        AmbiguousThreadMatch: Multiple threads match.
    """
    normalized = normalize_branch_name(partial_id)
    all_locs = list_all_threads(base, pattern=pattern)

    # Exact match
    exact = [loc for loc in all_locs if loc.meta.id == normalized]
    if len(exact) == 1:
        return exact[0]

    # Prefix match
    matches = [loc for loc in all_locs if loc.meta.id.startswith(normalized)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AmbiguousThreadMatch(partial_id, [loc.meta for loc in matches])

    available = [loc.meta for loc in all_locs]
    raise ThreadNotFoundError(partial_id, available)


def thread_dir_for_location(base: Path, loc: ThreadLocation) -> Path:
    """Return the thread directory path for a ThreadLocation."""
    if loc.archived:
        return archive_threads_root(base, loc.branch) / loc.meta.id
    return thread_dir(base, loc.branch, loc.meta.id)


def list_messages_from_dir(tdir: Path) -> list[Message]:
    """List all messages from a thread directory, in sequential order."""
    messages: list[Message] = []
    for path in sorted(tdir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        try:
            messages.append(parse_message(path))
        except (ValueError, FileNotFoundError):
            continue
    messages.sort(key=lambda m: m.sequence)
    return messages


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
        created_at = parse_iso_datetime(created_str)
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


def resolve_thread(
    base: Path,
    branch: str,
    partial_id: str,
    pattern: str | None = None,
) -> ThreadMeta:
    """Resolve a thread by exact or prefix match on its ID.

    Supports partial IDs so users can type ``council-cf`` instead of
    ``council-cfa4``.  When *pattern* is given, only threads of that
    pattern (e.g. ``"council"``) are considered.

    Args:
        base: Project root.
        branch: Branch name.
        partial_id: Full or prefix of a thread ID.
        pattern: Optional pattern filter (e.g. ``"council"``).

    Returns:
        ThreadMeta for the matched thread.

    Raises:
        ThreadNotFoundError: No thread matches *partial_id*.
        AmbiguousThreadMatch: Multiple threads match *partial_id*.
    """
    # Try exact match first
    tdir = thread_dir(base, branch, partial_id)
    if tdir.exists():
        meta = read_thread_meta(tdir)
        if pattern is None or meta.pattern == pattern:
            return meta

    # Prefix match across all threads
    all_threads = list_threads(base, branch)
    if pattern:
        all_threads = [t for t in all_threads if t.pattern == pattern]

    normalized = normalize_branch_name(partial_id)
    matches = [t for t in all_threads if t.id.startswith(normalized)]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AmbiguousThreadMatch(partial_id, matches)

    # No match — raise with available threads for suggestions
    raise ThreadNotFoundError(partial_id, all_threads)


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
    status: str | None = None,
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
        status: Optional status (complete, error, timeout, interrupted).

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
        status=status,
    )

    # Build frontmatter
    fm = serialize_frontmatter(
        [
            ("from", from_),
            ("to", to),
            ("timestamp", now.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("refs", refs or None),
            ("status", status),
        ]
    )
    lines = [fm, "", body, ""]

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
        timestamp = parse_iso_datetime(ts_str)
    else:
        timestamp = datetime.now(UTC)

    # Parse sequence from filename
    stem = path.stem  # e.g. "0001-king"
    try:
        seq = int(stem.split("-", 1)[0])
    except (ValueError, IndexError):
        seq = 0

    refs = fm.get("refs", [])
    status = fm.get("status")
    if status is not None:
        status = str(status)

    return Message(
        from_=str(fm.get("from", "")),
        to=str(fm.get("to", "")),
        body=body,
        timestamp=timestamp,
        refs=refs if isinstance(refs, list) else [],
        sequence=seq,
        status=status,
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


def is_interrupted_response(body: str) -> bool:
    """Check if a thread message body was interrupted before completion."""
    return "*[Interrupted" in body


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
    response_msgs: dict[str, Message] = {}
    for msg in messages:
        if msg.sequence > last_ask_seq and msg.from_ in expected:
            responded.add(msg.from_)
            response_msgs[msg.from_] = msg

    # Classify each expected member.
    # Prefer msg.status metadata; fall back to body-prefix sniffing for legacy messages.
    for name in expected:
        if name in responded:
            msg = response_msgs[name]
            if msg.status:
                if msg.status == "timeout":
                    member_states[name] = MemberState(state=MEMBER_TIMED_OUT, error=msg.body)
                elif msg.status in ("error", "interrupted"):
                    member_states[name] = MemberState(state=MEMBER_ERRORED, error=msg.body)
                else:
                    member_states[name] = MemberState(state=MEMBER_RESPONDED)
            elif is_timeout_response(msg.body):
                member_states[name] = MemberState(state=MEMBER_TIMED_OUT, error=msg.body)
            elif is_error_response(msg.body):
                member_states[name] = MemberState(state=MEMBER_ERRORED, error=msg.body)
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


def format_thread_history(tdir: Path, target_member: str, suffix: str | None = None) -> str:
    """Format thread messages as a multi-party conversation prompt.

    Reads all finalized messages from *tdir* in sequence order and returns
    a formatted transcript suitable for injecting into an agent prompt.

    Args:
        tdir: Thread directory path containing NNNN-*.md message files.
        target_member: Name of the member who will receive this prompt.
        suffix: Custom instruction appended after the history block.
            Defaults to "You are {target_member}. Continue the discussion."

    Returns:
        Formatted string with conversation history and instruction suffix.
    """
    messages: list[Message] = []
    for path in sorted(tdir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        try:
            messages.append(parse_message(path))
        except (ValueError, FileNotFoundError):
            continue
    messages.sort(key=lambda m: m.sequence)

    default_suffix = (
        f"You are {target_member}. Read the full conversation above before responding.\n"
        "\n"
        "This is a group discussion, not a survey. Engage with what others have said — "
        "agree, disagree, extend, or synthesize. Reference specific points rather than "
        "restating the question from scratch. If someone raised a concern you think is "
        "wrong, say so and explain why. If they made a point you hadn't considered, "
        "acknowledge it and build on it.\n"
        "\n"
        "Be direct and concise. The King is reading these — make your contribution count."
    )
    tail = suffix or default_suffix

    if not messages:
        return f"---\n{tail}"

    lines = ["[Previous conversation]", ""]
    for msg in messages:
        if msg.to not in ("all", "", "king"):
            header = f"{msg.from_} (to {msg.to}):"
        else:
            header = f"{msg.from_}:"
        lines.append(f"{header} {msg.body}")
        lines.append("")

    lines.append("---")
    lines.append(tail)

    return "\n".join(lines)


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
