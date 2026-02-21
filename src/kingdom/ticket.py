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

import hashlib
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from kingdom.parsing import parse_frontmatter, serialize_yaml_value

STATUSES = {"open", "in_progress", "in_review", "closed"}


@dataclass
class Ticket:
    """A ticket with YAML frontmatter metadata and markdown body."""

    id: str
    status: str  # open, in_progress, in_review, closed
    deps: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    created: datetime = field(default_factory=lambda: datetime.now(UTC))
    type: str = "task"  # task, bug, feature
    priority: int = 2  # 1-3, 1 is highest
    assignee: str | None = None
    title: str = ""
    body: str = ""
    # Optional fields that may be present in some tickets
    tags: list[str] = field(default_factory=list)
    parent: str | None = None
    external_ref: str | None = None
    duplicate_of: str | None = None


def clamp_priority(value: int | str | None) -> int:
    if value is None:
        return 2
    try:
        p = int(value)
    except (ValueError, TypeError):
        return 2
    return max(1, min(3, p))


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
        return [str(item) for item in value]
    return [str(value)]


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
        if created_str.endswith("Z"):
            created_str = created_str[:-1] + "+00:00"
        created = datetime.fromisoformat(created_str)
    else:
        created = datetime.now(UTC)

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
        priority=clamp_priority(frontmatter_dict.get("priority", 2)),
        assignee=str(frontmatter_dict.get("assignee")) if frontmatter_dict.get("assignee") else None,
        title=title,
        body=body,
        tags=tags,
        parent=str(frontmatter_dict.get("parent")) if frontmatter_dict.get("parent") else None,
        external_ref=(str(frontmatter_dict.get("external-ref")) if frontmatter_dict.get("external-ref") else None),
        duplicate_of=(str(frontmatter_dict.get("duplicate-of")) if frontmatter_dict.get("duplicate-of") else None),
    )


def serialize_ticket(ticket: Ticket) -> str:
    lines = ["---"]

    lines.append(f'id: "{ticket.id}"')
    lines.append(f"status: {ticket.status}")
    lines.append(f"deps: {serialize_yaml_value(ticket.deps)}")
    lines.append(f"links: {serialize_yaml_value(ticket.links)}")

    created_str = ticket.created.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"created: {created_str}")

    lines.append(f"type: {ticket.type}")
    lines.append(f"priority: {ticket.priority}")

    if ticket.assignee:
        lines.append(f"assignee: {ticket.assignee}")
    if ticket.external_ref:
        lines.append(f"external-ref: {ticket.external_ref}")
    if ticket.parent:
        lines.append(f"parent: {ticket.parent}")
    if ticket.tags:
        lines.append(f"tags: {serialize_yaml_value(ticket.tags)}")
    if ticket.duplicate_of:
        lines.append(f"duplicate-of: {ticket.duplicate_of}")

    lines.append("---")

    lines.append(f"# {ticket.title}")
    lines.append("")
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def collect_all_tickets(base: Path) -> list[Ticket]:
    """Collect all tickets across branches and backlog.

    Searches branches/*/tickets/ (skipping done branches) and backlog/tickets/.
    """
    from kingdom.state import backlog_root, branches_root

    all_tickets: list[Ticket] = []

    branches_dir = branches_root(base)
    if branches_dir.exists():
        for branch_dir in branches_dir.iterdir():
            if branch_dir.is_dir():
                state_path = branch_dir / "state.json"
                if state_path.exists():
                    import json

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

    return all_tickets


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


class AmbiguousTicketMatch(Exception):
    """Raised when a partial ID matches multiple tickets."""

    def __init__(self, partial_id: str, matches: list[tuple[Ticket, Path]]) -> None:
        self.partial_id = partial_id
        self.matches = matches
        match_ids = [t.id for t, _ in matches]
        super().__init__(f"Partial ID '{partial_id}' matches multiple tickets: {', '.join(match_ids)}")


def find_ticket(base: Path, partial_id: str, branch: str | None = None) -> tuple[Ticket, Path] | None:
    """Find a ticket by full ID or prefix across branch/backlog/archive locations."""
    from kingdom.state import archive_root, backlog_root, branch_root, branches_root

    search_id = partial_id.lower()
    if search_id.startswith("kin-"):
        search_id = search_id[4:]

    matches: list[tuple[Ticket, Path]] = []
    search_dirs: list[Path] = []

    if branch:
        scoped = branch_root(base, branch) / "tickets"
        if scoped.exists():
            search_dirs.append(scoped)
    else:
        branches_dir = branches_root(base)
        if branches_dir.exists():
            for branch_dir in branches_dir.iterdir():
                if branch_dir.is_dir():
                    tickets_dir = branch_dir / "tickets"
                    if tickets_dir.exists():
                        search_dirs.append(tickets_dir)

    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        search_dirs.append(backlog_tickets)

    archive_dir = archive_root(base)
    if archive_dir.exists():
        for archive_item in archive_dir.iterdir():
            if archive_item.is_dir():
                tickets_dir = archive_item / "tickets"
                if tickets_dir.exists():
                    search_dirs.append(tickets_dir)

    for search_dir in search_dirs:
        for ticket_file in search_dir.glob("*.md"):
            file_id = ticket_file.stem.lower()
            if file_id.startswith("kin-"):
                file_id_suffix = file_id[4:]
            else:
                file_id_suffix = file_id

            if file_id_suffix.startswith(search_id) or file_id.startswith(f"kin-{search_id}"):
                try:
                    ticket = read_ticket(ticket_file)
                    matches.append((ticket, ticket_file))
                except (ValueError, FileNotFoundError):
                    continue

    if not matches:
        return None

    if len(matches) > 1:
        raise AmbiguousTicketMatch(partial_id, matches)

    return matches[0]


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


def append_worklog_entry(
    path: Path,
    message: str,
    timestamp: datetime | None = None,
    timestamp_text: str | None = None,
) -> str:
    """Append to the ticket's ``## Worklog`` section (created if missing).

    Works on raw markdown to avoid round-trip issues with frontmatter parsing.
    """
    if not path.exists():
        raise FileNotFoundError(f"Ticket file not found: {path}")

    if timestamp is None:
        timestamp = datetime.now(UTC)

    if timestamp_text is None:
        timestamp_text = timestamp.strftime("%Y-%m-%d %H:%M")
    entry = f"- {timestamp_text} — {message}"

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    worklog_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Worklog":
            worklog_idx = i
            break

    if worklog_idx is not None:
        insert_idx = len(lines)
        for i in range(worklog_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                insert_idx = i
                break

        actual_insert = insert_idx
        while actual_insert > worklog_idx + 1 and lines[actual_insert - 1].strip() == "":
            actual_insert -= 1

        lines.insert(actual_insert, entry)
        if actual_insert + 1 < len(lines) and lines[actual_insert + 1].strip() != "":
            lines.insert(actual_insert + 1, "")
    else:
        while lines and lines[-1].strip() == "":
            lines.pop()
        lines.append("")
        lines.append("## Worklog")
        lines.append("")
        lines.append(entry)

    if lines and lines[-1] != "":
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return entry


def get_ticket_location(base: Path, ticket_id: str) -> Path | None:
    result = find_ticket(base, ticket_id)
    if result is None:
        return None
    return result[1]
