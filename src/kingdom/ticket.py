"""Ticket model for integrated ticket management.

This module provides the Ticket dataclass and functions for parsing,
serializing, reading, and writing ticket files. Ticket files use YAML
frontmatter followed by markdown content.

Example ticket file format:
    ---
    id: kin-a1b2
    status: open
    deps: []
    links: []
    created: 2026-02-04T16:00:00Z
    type: task
    priority: 2
    assignee: Jim Robinson-Bohnslav
    ---
    # Ticket title

    Body content here.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from kingdom.parsing import parse_frontmatter, parse_iso_datetime, serialize_frontmatter
from kingdom.state import flock

STATUSES = {"open", "in_progress", "in_review", "closed"}
TICKET_TYPES = {"task", "bug", "feature", "epic"}
# Terminal outcomes written by ``kd tk close --resolution``.
TICKET_RESOLUTIONS = ("completed", "wont-do", "duplicate", "superseded", "invalid")


@dataclass
class Ticket:
    """A ticket with YAML frontmatter metadata and markdown body."""

    id: str
    status: str  # open, in_progress, in_review, closed
    deps: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    created: datetime = field(default_factory=lambda: datetime.now(UTC))
    type: str = "task"  # task, bug, feature, epic
    priority: int = 2  # 0-3, 0 is highest
    assignee: str | None = None
    title: str = ""
    body: str = ""
    closed_at: datetime | None = None
    resolution: str | None = None
    close_reason: str | None = None
    # Stable execution-context ID that invoked close, when one was available.
    closed_context: str | None = None
    # Optional fields that may be present in some tickets
    tags: list[str] = field(default_factory=list)
    parent: str | None = None
    external_ref: str | None = None
    duplicate_of: str | None = None
    superseded_by: str | None = None


def clamp_priority(value: int | str | None) -> int:
    if value is None:
        return 2
    if isinstance(value, str):
        value = value.strip()
        if value.lower().startswith("p") and value[1:].isdigit():
            value = value[1:]
    try:
        p = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid priority: {value!r} (expected 0-3 or p0-p3)") from None
    if p < 0 or p > 3:
        raise ValueError(f"Priority out of range: {p} (expected 0-3)")
    return p


def safe_clamp_priority(value: int | str | None) -> int:
    """Like clamp_priority but defaults to 2 on invalid input.

    Used when parsing existing ticket files where a bad priority
    shouldn't crash the system.
    """
    try:
        return clamp_priority(value)
    except ValueError:
        return 2


def generate_ticket_id(tickets_dir: Path | None = None) -> str:
    """Generate a unique 4-character hex ticket ID."""
    max_attempts = 100

    for _ in range(max_attempts):
        entropy = f"{os.getpid()}{datetime.now().timestamp()}{os.urandom(4).hex()}"
        ticket_id = hashlib.sha256(entropy.encode()).hexdigest()[:4]

        if tickets_dir is not None and (
            (tickets_dir / f"{ticket_id}.md").exists() or (tickets_dir / f"kin-{ticket_id}.md").exists()
        ):
            continue

        return ticket_id

    raise RuntimeError(f"Failed to generate unique ticket ID after {max_attempts} attempts")


def coerce_to_str_list(value: str | int | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    return list(dict.fromkeys(items))


def parse_close_reason(content: str, value: object) -> str | None:
    """Decode JSON quoting only for the ticket ``close_reason`` field."""
    if not value:
        return None

    frontmatter = content.split("---", 2)[1]
    match = re.search(r"^close_reason:\s*(.*)$", frontmatter, flags=re.MULTILINE)
    if match is None or not match.group(1).startswith('"'):
        return str(value)

    try:
        decoded = json.loads(match.group(1))
    except json.JSONDecodeError:
        return str(value)
    return str(decoded)


def parse_ticket(content: str) -> Ticket:
    frontmatter_dict, body_content = parse_frontmatter(content)

    title = ""
    body_lines = body_content.split("\n")
    body_start = 0
    for i, line in enumerate(body_lines):
        if line.startswith("# "):
            title = line[2:].strip()
            body_start = i + 1
            break

    body = "\n".join(body_lines[body_start:]).strip()

    created_str = frontmatter_dict.get("created")
    if created_str and isinstance(created_str, str):
        created = parse_iso_datetime(created_str)
    else:
        created = datetime.now(UTC)

    closed_at_str = frontmatter_dict.get("closed_at")
    closed_at: datetime | None = None
    if closed_at_str and isinstance(closed_at_str, str):
        closed_at = parse_iso_datetime(closed_at_str)

    deps = coerce_to_str_list(frontmatter_dict.get("deps", []))
    links = coerce_to_str_list(frontmatter_dict.get("links", []))
    tags = coerce_to_str_list(frontmatter_dict.get("tags", []))

    return Ticket(
        id=str(frontmatter_dict.get("id", "")),
        status=str(frontmatter_dict.get("status", "open")),
        deps=deps,
        links=links,
        created=created,
        type=str(frontmatter_dict.get("type", "task")),
        priority=safe_clamp_priority(frontmatter_dict.get("priority", 2)),
        assignee=str(frontmatter_dict.get("assignee")) if frontmatter_dict.get("assignee") else None,
        title=title,
        body=body,
        closed_at=closed_at,
        resolution=(str(frontmatter_dict.get("resolution")) if frontmatter_dict.get("resolution") else None),
        close_reason=parse_close_reason(content, frontmatter_dict.get("close_reason")),
        closed_context=(
            str(frontmatter_dict.get("closed_context")) if frontmatter_dict.get("closed_context") else None
        ),
        tags=tags,
        parent=str(frontmatter_dict.get("parent")) if frontmatter_dict.get("parent") else None,
        external_ref=(str(frontmatter_dict.get("external-ref")) if frontmatter_dict.get("external-ref") else None),
        duplicate_of=(str(frontmatter_dict.get("duplicate-of")) if frontmatter_dict.get("duplicate-of") else None),
        superseded_by=(str(frontmatter_dict.get("superseded-by")) if frontmatter_dict.get("superseded-by") else None),
    )


def serialize_ticket(ticket: Ticket) -> str:
    created_str = ticket.created.strftime("%Y-%m-%dT%H:%M:%SZ")
    closed_str = ticket.closed_at.strftime("%Y-%m-%dT%H:%M:%SZ") if ticket.closed_at else None

    fm = serialize_frontmatter(
        [
            ("id", f'"{ticket.id}"'),
            ("status", ticket.status),
            ("deps", ticket.deps),
            ("links", ticket.links),
            ("created", created_str),
            ("type", ticket.type),
            ("priority", ticket.priority),
            ("closed_at", closed_str),
            ("resolution", ticket.resolution),
            ("close_reason", json.dumps(ticket.close_reason, ensure_ascii=False) if ticket.close_reason else None),
            ("closed_context", ticket.closed_context),
            ("assignee", ticket.assignee),
            ("external-ref", ticket.external_ref),
            ("parent", ticket.parent),
            ("tags", ticket.tags or None),
            ("duplicate-of", ticket.duplicate_of),
            ("superseded-by", ticket.superseded_by),
        ]
    )

    lines = [fm, f"# {ticket.title}", ""]
    if ticket.body:
        lines.append(ticket.body)
        lines.append("")

    return "\n".join(lines)


def read_ticket(path: Path) -> Ticket:
    if not path.exists():
        raise FileNotFoundError(f"Ticket file not found: {path}")

    content = path.read_text(encoding="utf-8")
    return parse_ticket(content)


def write_ticket(ticket: Ticket, path: Path) -> None:
    content = serialize_ticket(ticket)
    write_ticket_content(path, content)


def write_ticket_content(path: Path, content: str) -> None:
    """Atomically replace a ticket so an interrupted write leaves the original intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        if path.exists():
            temporary.chmod(path.stat().st_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def replace_ticket_assignee(content: str, assignee: str) -> str:
    """Change only the assignee line while preserving the rest of a ticket verbatim."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("Content must start with YAML frontmatter (---)")

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise ValueError("Invalid frontmatter: missing closing ---")

    for index in range(1, closing_index):
        if lines[index].partition(":")[0].strip() != "assignee":
            continue
        newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
        if not lines[index].endswith(("\n", "\r")):
            newline = ""
        lines[index] = f"assignee: {assignee}{newline}"
        return "".join(lines)

    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    lines.insert(closing_index, f"assignee: {assignee}{newline}")
    return "".join(lines)


def write_ticket_assignee(path: Path, assignee: str) -> None:
    """Persist a migration-only assignee change without canonicalizing Markdown."""
    lock_path = path.parent / f".{path.name}.lock"
    with flock(lock_path):
        content = path.read_text(encoding="utf-8")
        updated = replace_ticket_assignee(content, assignee)
        if updated != content:
            write_ticket_content(path, updated)


def list_tickets(directory: Path) -> list[Ticket]:
    if not directory.exists():
        return []

    tickets: list[Ticket] = []
    for ticket_file in directory.glob("*.md"):
        try:
            ticket = read_ticket(ticket_file)
            tickets.append(ticket)
        except (ValueError, FileNotFoundError):
            continue

    tickets.sort(key=lambda t: (t.priority, t.created))
    return tickets


def collect_all_tickets(base: Path, *, include_archive: bool = False, include_done: bool = False) -> list[Ticket]:
    """Collect all tickets across branches, backlog, and optionally archive.

    Searches branches/*/tickets/ (skipping done branches unless include_done=True)
    and backlog/tickets/.
    With include_archive=True, also searches archive/*/tickets/.
    """
    from kingdom.state import archive_root, backlog_root, branches_root

    all_tickets: list[Ticket] = []

    branches_dir = branches_root(base)
    if branches_dir.exists():
        for branch_dir in branches_dir.iterdir():
            if branch_dir.is_dir():
                state_path = branch_dir / "state.json"
                if not include_done and state_path.exists():
                    try:
                        state = json.loads(state_path.read_text())
                        if state.get("status") == "done":
                            continue
                    except (json.JSONDecodeError, OSError):
                        pass

                tickets_dir = branch_dir / "tickets"
                if tickets_dir.exists():
                    all_tickets.extend(list_tickets(tickets_dir))

    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        all_tickets.extend(list_tickets(backlog_tickets))

    if include_archive:
        archive_dir = archive_root(base)
        if archive_dir.exists():
            for archive_item in archive_dir.iterdir():
                if archive_item.is_dir():
                    tickets_dir = archive_item / "tickets"
                    if tickets_dir.exists():
                        all_tickets.extend(list_tickets(tickets_dir))

    # Deduplicate by ID — branches are collected first, so they win
    seen: set[str] = set()
    deduped: list[Ticket] = []
    for t in all_tickets:
        if t.id not in seen:
            seen.add(t.id)
            deduped.append(t)
    return deduped


def find_newly_unblocked(closed_ticket_id: str, base: Path) -> list[Ticket]:
    """Find tickets that become unblocked when a ticket is closed.

    A ticket is "newly unblocked" if:
    - It has the closed ticket as a dependency
    - It is not itself closed
    - All of its dependencies are now closed

    Args:
        closed_ticket_id: ID of the ticket that was just closed.
        base: Project root directory.

    Returns:
        List of tickets that are now unblocked.
    """
    all_tickets = collect_all_tickets(base)

    status_by_id = {t.id: t.status for t in all_tickets}
    status_by_id[closed_ticket_id] = "closed"

    newly_unblocked = []
    for ticket in all_tickets:
        if ticket.status == "closed":
            continue
        if closed_ticket_id not in ticket.deps:
            continue
        all_deps_closed = all(status_by_id.get(dep, "unknown") == "closed" for dep in ticket.deps)
        if all_deps_closed:
            newly_unblocked.append(ticket)

    return newly_unblocked


class TicketMatch:
    """Result from find_ticket — backward-compatible with ``ticket, path = result`` unpacking.

    Supports 2-tuple unpacking (ticket, path) for existing callers,
    plus a ``.location`` attribute for the search origin.
    """

    __slots__ = ("location", "path", "ticket")

    def __init__(self, ticket: Ticket, path: Path, location: str) -> None:
        self.ticket = ticket
        self.path = path
        self.location = location

    def __iter__(self):
        yield self.ticket
        yield self.path

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> Ticket | Path:
        if index == 0:
            return self.ticket
        if index == 1:
            return self.path
        raise IndexError(index)

    def __repr__(self) -> str:
        return f"TicketMatch(ticket={self.ticket!r}, path={self.path!r}, location={self.location!r})"


class AmbiguousTicketMatch(Exception):
    """Raised when a partial ID matches multiple tickets."""

    def __init__(self, partial_id: str, matches: list[TicketMatch]) -> None:
        self.partial_id = partial_id
        self.matches = matches
        match_ids = [m.ticket.id for m in matches]
        super().__init__(f"Partial ID '{partial_id}' matches multiple tickets: {', '.join(match_ids)}")


def find_ticket(base: Path, partial_id: str, branch: str | None = None) -> TicketMatch | None:
    """Find a ticket by full ID or prefix across branch/backlog/archive locations."""
    from kingdom.state import archive_root, backlog_root, branch_root, branches_root

    search_id = partial_id.lower()
    if search_id.startswith("kin-"):
        search_id = search_id[4:]

    matches: list[TicketMatch] = []
    search_dirs: list[tuple[Path, str]] = []

    if branch:
        scoped = branch_root(base, branch) / "tickets"
        if scoped.exists():
            search_dirs.append((scoped, f"branch:{branch}"))
    else:
        # Put current branch first so dedup prefers it
        from kingdom.state import resolve_current_run

        current: str | None = None
        with contextlib.suppress(Exception):
            current = resolve_current_run(base)

        branches_dir = branches_root(base)
        if branches_dir.exists():
            if current:
                current_tickets = branch_root(base, current) / "tickets"
                if current_tickets.exists():
                    search_dirs.append((current_tickets, f"branch:{current}"))

            for branch_dir in branches_dir.iterdir():
                if branch_dir.is_dir() and branch_dir.name != current:
                    tickets_dir = branch_dir / "tickets"
                    if tickets_dir.exists():
                        search_dirs.append((tickets_dir, f"branch:{branch_dir.name}"))

    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        search_dirs.append((backlog_tickets, "backlog"))

    archive_dir = archive_root(base)
    if archive_dir.exists():
        for archive_item in archive_dir.iterdir():
            if archive_item.is_dir():
                tickets_dir = archive_item / "tickets"
                if tickets_dir.exists():
                    search_dirs.append((tickets_dir, f"archive:{archive_item.name}"))

    for search_dir, location in search_dirs:
        for ticket_file in search_dir.glob("*.md"):
            file_id = ticket_file.stem.lower()
            if file_id.startswith("kin-"):
                file_id_suffix = file_id[4:]
            else:
                file_id_suffix = file_id

            if file_id_suffix.startswith(search_id) or file_id.startswith(f"kin-{search_id}"):
                try:
                    ticket = read_ticket(ticket_file)
                    matches.append(TicketMatch(ticket, ticket_file, location))
                except (ValueError, FileNotFoundError):
                    continue

    if not matches:
        return None

    # Deduplicate by ticket ID — keep first occurrence (branch → backlog → archive)
    seen: set[str] = set()
    deduped: list[TicketMatch] = []
    for m in matches:
        if m.ticket.id not in seen:
            seen.add(m.ticket.id)
            deduped.append(m)

    if len(deduped) > 1:
        raise AmbiguousTicketMatch(partial_id, deduped)

    return deduped[0]


def move_ticket(ticket_path: Path, dest_dir: Path) -> Path:
    if not ticket_path.exists():
        raise FileNotFoundError(f"Ticket file not found: {ticket_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    new_path = dest_dir / ticket_path.name
    if new_path.exists():
        raise FileExistsError(f"Destination already exists: {new_path}")
    try:
        ticket_path.rename(new_path)
    except OSError:
        # Cross-filesystem rename; fall back to copy-then-delete
        shutil.copy2(str(ticket_path), str(new_path))
        ticket_path.unlink()
    return new_path


def insert_markdown_section_entry(content: str, section: str, entry: str) -> str:
    """Append an entry to a second-level Markdown section, creating it if needed."""
    heading = f"## {section}"
    lines = content.split("\n")

    section_index = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            section_index = index
            break

    if section_index is not None:
        insert_index = len(lines)
        for index in range(section_index + 1, len(lines)):
            if lines[index].startswith("## "):
                insert_index = index
                break

        while insert_index > section_index + 1 and lines[insert_index - 1].strip() == "":
            insert_index -= 1

        lines.insert(insert_index, entry)
        if insert_index + 1 < len(lines) and lines[insert_index + 1].strip() != "":
            lines.insert(insert_index + 1, "")
    else:
        while lines and lines[-1].strip() == "":
            lines.pop()
        lines.extend(["", heading, "", entry])

    if lines and lines[-1] != "":
        lines.append("")

    return "\n".join(lines)


def insert_worklog_entry(content: str, entry: str) -> str:
    """Insert an entry into the ``## Worklog`` section of ticket markdown.

    Pure string transform — finds the ``## Worklog`` heading, inserts the entry
    at the end of that section (before the next ``## `` heading or EOF), and
    returns the new content.  Creates the section if it doesn't exist.
    """
    return insert_markdown_section_entry(content, "Worklog", entry)


def effective_resolution(ticket: Ticket) -> str | None:
    """Return the active resolution, including legacy closed-ticket inference."""
    if ticket.status != "closed":
        return None
    if ticket.resolution:
        return ticket.resolution
    if ticket.duplicate_of:
        return "duplicate"
    if ticket.superseded_by:
        return "superseded"
    return "completed"


def effective_close_reason(ticket: Ticket) -> str | None:
    """Return the active reason, deriving it for legacy reference-based closures."""
    if ticket.status != "closed":
        return None
    if ticket.close_reason and ticket.close_reason.strip():
        return ticket.close_reason.strip()
    if ticket.resolution is None:
        if ticket.duplicate_of:
            return f"Duplicate of {ticket.duplicate_of}"
        if ticket.superseded_by:
            return f"Superseded by {ticket.superseded_by}"
    return None


def validate_terminal_evidence(ticket: Ticket) -> list[str]:
    """Return validation errors for a ticket's active terminal evidence."""
    if ticket.status != "closed":
        return [f"status is {ticket.status}, expected closed"]

    resolution = effective_resolution(ticket)
    if resolution not in TICKET_RESOLUTIONS:
        return [f"unknown resolution '{resolution}'"]

    errors = []
    if resolution != "completed" and effective_close_reason(ticket) is None:
        errors.append(f"resolution {resolution} requires close_reason")

    if resolution == "duplicate":
        if not ticket.duplicate_of:
            errors.append("resolution duplicate requires duplicate-of")
        if ticket.superseded_by:
            errors.append("resolution duplicate cannot also set superseded-by")
    elif resolution == "superseded":
        if not ticket.superseded_by:
            errors.append("resolution superseded requires superseded-by")
        if ticket.duplicate_of:
            errors.append("resolution superseded cannot also set duplicate-of")
    elif ticket.duplicate_of or ticket.superseded_by:
        errors.append(f"resolution {resolution} cannot use duplicate-of or superseded-by")

    return errors


def append_worklog_entry(
    path: Path,
    message: str,
    timestamp: datetime | None = None,
    timestamp_text: str | None = None,
    author: str | None = None,
) -> str:
    """Append to the ticket's ``## Worklog`` section (created if missing).

    Thin I/O wrapper around :func:`insert_worklog_entry`.
    """
    if not path.exists():
        raise FileNotFoundError(f"Ticket file not found: {path}")

    if timestamp is None:
        timestamp = datetime.now(UTC)

    if timestamp_text is None:
        local_ts = timestamp.astimezone()
        timestamp_text = f"[{local_ts.strftime('%Y-%m-%d %H:%M')}]"

    # Indent continuation lines so multiline entries render as grouped bullets
    lines = message.split("\n")
    first = lines[0]
    rest = [f"  {line}" for line in lines[1:]]
    formatted = "\n".join([first, *rest])
    author_tag = f" [{author}]" if author else ""
    entry = f"- {timestamp_text}{author_tag} — {formatted}"

    lock_path = path.parent / f".{path.name}.lock"
    with flock(lock_path):
        content = path.read_text(encoding="utf-8")
        new_content = insert_worklog_entry(content, entry)
        write_ticket_content(path, new_content)
    return entry


def get_ticket_location(base: Path, ticket_id: str) -> Path | None:
    result = find_ticket(base, ticket_id)
    if result is None:
        return None
    return result[1]


# ---------------------------------------------------------------------------
# Pure filtering functions (no I/O, no CLI deps)
# ---------------------------------------------------------------------------


def filter_tickets_by_status(
    tickets: list[Ticket],
    status: str | None,
    include_closed: bool,
) -> list[Ticket]:
    """Filter tickets by explicit status or exclude closed tickets."""
    if status is not None:
        return [ticket for ticket in tickets if ticket.status == status]
    if not include_closed:
        return [ticket for ticket in tickets if ticket.status != "closed"]
    return tickets


def filter_tickets(
    tickets: list[Ticket],
    *,
    assignee: str | None = None,
    tag: str | None = None,
    priority: int | None = None,
) -> list[Ticket]:
    """Filter tickets by assignee, tag, and/or priority."""
    result = tickets
    if assignee:
        result = [t for t in result if t.assignee == assignee]
    if tag:
        result = [t for t in result if tag in t.tags]
    if priority is not None:
        result = [t for t in result if t.priority == priority]
    return result


def filter_tickets_by_deps(
    tickets: list[Ticket],
    status_by_id: dict[str, str],
    *,
    ready: bool = False,
    blocked: bool = False,
) -> list[Ticket]:
    """Filter tickets by dependency status (ready or blocked).

    - ready: tickets with no open deps and status is open (startable, not already started)
    - blocked: tickets with at least one open dep
    """
    if not ready and not blocked:
        return tickets
    result = []
    for t in tickets:
        if t.status == "closed":
            continue
        has_open_dep = any(status_by_id.get(d, "unknown") != "closed" for d in t.deps)
        if (ready and not has_open_dep and t.status == "open") or (blocked and has_open_dep):
            result.append(t)
    return result


def collect_tickets_by_location(
    base: Path,
    *,
    include_done: bool = False,
    include_archive: bool = False,
) -> list[tuple[str, Ticket]]:
    """Collect tickets from all branches and backlog with location labels.

    Returns a list of ``(location_label, ticket)`` pairs where location_label
    is e.g. ``"branch:feature-foo"``, ``"backlog"``, or ``"archive:backlog"``.
    """
    import json as _json

    from kingdom.state import archive_root, backlog_root, branches_root

    pairs: list[tuple[str, Ticket]] = []

    branches_dir = branches_root(base)
    if branches_dir.exists():
        for branch_dir in branches_dir.iterdir():
            if not branch_dir.is_dir():
                continue
            if not include_done:
                state_path = branch_dir / "state.json"
                if state_path.exists():
                    try:
                        state = _json.loads(state_path.read_text())
                        if state.get("status") == "done":
                            continue
                    except (_json.JSONDecodeError, OSError):
                        pass
            tickets_dir = branch_dir / "tickets"
            if tickets_dir.exists():
                label = f"branch:{branch_dir.name}"
                for ticket in list_tickets(tickets_dir):
                    pairs.append((label, ticket))

    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        for ticket in list_tickets(backlog_tickets):
            pairs.append(("backlog", ticket))

    if include_archive:
        archive_dir = archive_root(base)
        if archive_dir.exists():
            for archive_item in archive_dir.iterdir():
                if not archive_item.is_dir():
                    continue
                tickets_dir = archive_item / "tickets"
                if tickets_dir.exists():
                    label = f"archive:{archive_item.name}"
                    for ticket in list_tickets(tickets_dir):
                        pairs.append((label, ticket))

    return pairs


# ---------------------------------------------------------------------------
# Worklog author parsing and filtering
# ---------------------------------------------------------------------------

# Matches tagged worklog entries in both bracketed and unbracketed timestamp forms:
#   - [HH:MM] [author] — ...
#   - [YYYY-MM-DD HH:MM] [author] — ...
#   - YYYY-MM-DD HH:MM [author] — ...  (legacy unbracketed)
WORKLOG_AUTHOR_RE = re.compile(r"^- (?:\[[\d:. -]+\]|[\d][\d:. -]+\d)\s+\[([^\]]+)\]\s+—")


def parse_worklog_author(line: str) -> str:
    """Extract the author tag from a worklog line.

    Returns the author string if present, or ``"unknown"`` for legacy
    untagged entries.
    """
    m = WORKLOG_AUTHOR_RE.match(line)
    if m:
        return m.group(1)
    return "unknown"


def filter_worklog_lines(lines: list[str], *, show_all: bool = False) -> list[str]:
    """Filter worklog lines to lord-relevant entries.

    By default keeps ``lord-*`` and ``unknown`` (legacy) entries.
    With ``show_all=True``, returns all lines unfiltered.

    Continuation lines (indented, starting with spaces) follow their
    parent bullet.
    """
    if show_all:
        return lines

    result: list[str] = []
    include_current = False

    for line in lines:
        if line.startswith("- "):
            author = parse_worklog_author(line)
            include_current = author == "unknown" or author.startswith("lord-")
        # else: continuation line — follows parent bullet's include decision

        if include_current:
            result.append(line)

    return result
