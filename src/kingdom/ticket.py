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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from kingdom.parsing import parse_frontmatter, serialize_yaml_value


@dataclass
class Ticket:
    """A ticket with YAML frontmatter metadata and markdown body."""

    id: str
    status: str  # open, in_progress, closed
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


def clamp_priority(value: int | str | None) -> int:
    """Clamp priority to valid range (1-3).

    Args:
        value: Priority value (may be int, str, or None).

    Returns:
        Integer priority clamped to 1-3 range. Defaults to 2 if None or invalid.
    """
    if value is None:
        return 2
    try:
        p = int(value)
    except (ValueError, TypeError):
        return 2
    return max(1, min(3, p))


def generate_ticket_id(tickets_dir: Path | None = None) -> str:
    """Generate a unique ticket ID in the format 'kin-XXXX'.

    Args:
        tickets_dir: Optional path to tickets directory to check for collisions.
                    If provided, will regenerate ID if collision detected.

    Returns:
        A ticket ID string like 'kin-a1b2'.
    """
    max_attempts = 100

    for _ in range(max_attempts):
        # Generate 4 hex chars from timestamp + PID + random bytes
        entropy = f"{os.getpid()}{datetime.now().timestamp()}{os.urandom(4).hex()}"
        hash_bytes = hashlib.sha256(entropy.encode()).hexdigest()[:4]
        ticket_id = f"kin-{hash_bytes}"

        # Check for collisions if tickets_dir provided
        if tickets_dir is not None:
            ticket_path = tickets_dir / f"{ticket_id}.md"
            if ticket_path.exists():
                continue  # Collision, try again

        return ticket_id

    raise RuntimeError(f"Failed to generate unique ticket ID after {max_attempts} attempts")


def parse_ticket(content: str) -> Ticket:
    """Parse ticket content from YAML frontmatter + markdown body.

    Args:
        content: The full ticket file content.

    Returns:
        A Ticket instance.

    Raises:
        ValueError: If the content doesn't have valid frontmatter.
    """
    frontmatter_dict, body_content = parse_frontmatter(content)

    # Extract title from body (first # heading)
    title = ""
    body_lines = body_content.split("\n")
    body_start = 0
    for i, line in enumerate(body_lines):
        if line.startswith("# "):
            title = line[2:].strip()
            body_start = i + 1
            break

    # Everything after the title is the body
    body = "\n".join(body_lines[body_start:]).strip()

    # Parse created datetime
    created_str = frontmatter_dict.get("created")
    if created_str and isinstance(created_str, str):
        # Parse ISO format with Z suffix
        if created_str.endswith("Z"):
            created_str = created_str[:-1] + "+00:00"
        created = datetime.fromisoformat(created_str)
    else:
        created = datetime.now(UTC)

    # Build Ticket
    deps = frontmatter_dict.get("deps", [])
    links = frontmatter_dict.get("links", [])
    tags = frontmatter_dict.get("tags", [])

    return Ticket(
        id=str(frontmatter_dict.get("id", "")),
        status=str(frontmatter_dict.get("status", "open")),
        deps=deps if isinstance(deps, list) else [],
        links=links if isinstance(links, list) else [],
        created=created,
        type=str(frontmatter_dict.get("type", "task")),
        priority=clamp_priority(frontmatter_dict.get("priority", 2)),
        assignee=str(frontmatter_dict.get("assignee")) if frontmatter_dict.get("assignee") else None,
        title=title,
        body=body,
        tags=tags if isinstance(tags, list) else [],
        parent=str(frontmatter_dict.get("parent")) if frontmatter_dict.get("parent") else None,
        external_ref=(str(frontmatter_dict.get("external-ref")) if frontmatter_dict.get("external-ref") else None),
    )


def serialize_ticket(ticket: Ticket) -> str:
    """Convert a Ticket back to YAML frontmatter + markdown format.

    Args:
        ticket: The Ticket to serialize.

    Returns:
        The ticket content as a string.
    """
    lines = ["---"]

    # Required fields in standard order
    lines.append(f"id: {ticket.id}")
    lines.append(f"status: {ticket.status}")
    lines.append(f"deps: {serialize_yaml_value(ticket.deps)}")
    lines.append(f"links: {serialize_yaml_value(ticket.links)}")

    # Format datetime as ISO with Z suffix
    created_str = ticket.created.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"created: {created_str}")

    lines.append(f"type: {ticket.type}")
    lines.append(f"priority: {ticket.priority}")

    # Optional fields
    if ticket.assignee:
        lines.append(f"assignee: {ticket.assignee}")
    if ticket.external_ref:
        lines.append(f"external-ref: {ticket.external_ref}")
    if ticket.parent:
        lines.append(f"parent: {ticket.parent}")
    if ticket.tags:
        lines.append(f"tags: {serialize_yaml_value(ticket.tags)}")

    lines.append("---")

    # Add title and body
    lines.append(f"# {ticket.title}")
    lines.append("")
    if ticket.body:
        lines.append(ticket.body)
        lines.append("")

    return "\n".join(lines)


def read_ticket(path: Path) -> Ticket:
    """Read and parse a ticket file.

    Args:
        path: Path to the ticket file.

    Returns:
        A Ticket instance.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file content is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Ticket file not found: {path}")

    content = path.read_text(encoding="utf-8")
    return parse_ticket(content)


def write_ticket(ticket: Ticket, path: Path) -> None:
    """Write a ticket to a file.

    Args:
        ticket: The Ticket to write.
        path: Path where to write the ticket file.
    """
    content = serialize_ticket(ticket)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def list_tickets(directory: Path) -> list[Ticket]:
    """List all tickets in a directory, sorted by priority then created date.

    Args:
        directory: Path to the directory containing ticket files.

    Returns:
        List of Ticket objects sorted by priority (ascending, 1 is highest)
        then by created date (ascending, oldest first).
    """
    if not directory.exists():
        return []

    tickets: list[Ticket] = []
    for ticket_file in directory.glob("*.md"):
        try:
            ticket = read_ticket(ticket_file)
            tickets.append(ticket)
        except (ValueError, FileNotFoundError):
            # Skip invalid ticket files
            continue

    # Sort by priority (ascending) then created date (ascending)
    tickets.sort(key=lambda t: (t.priority, t.created))
    return tickets


class AmbiguousTicketMatch(Exception):
    """Raised when a partial ID matches multiple tickets."""

    def __init__(self, partial_id: str, matches: list[tuple[Ticket, Path]]) -> None:
        self.partial_id = partial_id
        self.matches = matches
        match_ids = [t.id for t, _ in matches]
        super().__init__(f"Partial ID '{partial_id}' matches multiple tickets: {', '.join(match_ids)}")


def find_ticket(base: Path, partial_id: str, branch: str | None = None) -> tuple[Ticket, Path] | None:
    """Find a ticket by partial ID matching.

    Searches across branches/*/tickets/, backlog/tickets/, and archive/*/tickets/.
    Partial IDs can be specified with or without the 'kin-' prefix.

    Args:
        base: Project root directory.
        partial_id: Full or partial ticket ID (e.g., "a1b2" or "kin-a1b2").
        branch: If provided, only search this branch's tickets and the backlog
            (not all branches). Useful for scoping peasant commands to the
            current feature branch.

    Returns:
        Tuple of (Ticket, Path) if found, None if not found.

    Raises:
        AmbiguousTicketMatch: If multiple tickets match the partial ID.
    """
    # Import here to avoid circular imports
    from kingdom.state import archive_root, backlog_root, branch_root, branches_root

    # Normalize partial_id: remove 'kin-' prefix if present for matching
    search_id = partial_id.lower()
    if search_id.startswith("kin-"):
        search_id = search_id[4:]

    matches: list[tuple[Ticket, Path]] = []

    # Build list of directories to search
    search_dirs: list[Path] = []

    if branch:
        # Scoped search: only current branch + backlog
        scoped = branch_root(base, branch) / "tickets"
        if scoped.exists():
            search_dirs.append(scoped)
    else:
        # Unscoped: all branches
        branches_dir = branches_root(base)
        if branches_dir.exists():
            for branch_dir in branches_dir.iterdir():
                if branch_dir.is_dir():
                    tickets_dir = branch_dir / "tickets"
                    if tickets_dir.exists():
                        search_dirs.append(tickets_dir)

    # backlog/tickets/
    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        search_dirs.append(backlog_tickets)

    # archive/*/tickets/
    archive_dir = archive_root(base)
    if archive_dir.exists():
        for archive_item in archive_dir.iterdir():
            if archive_item.is_dir():
                tickets_dir = archive_item / "tickets"
                if tickets_dir.exists():
                    search_dirs.append(tickets_dir)

    # Search all directories
    for search_dir in search_dirs:
        for ticket_file in search_dir.glob("*.md"):
            # Check if filename matches (kin-XXXX.md)
            file_id = ticket_file.stem.lower()
            if file_id.startswith("kin-"):
                file_id_suffix = file_id[4:]
            else:
                file_id_suffix = file_id

            # Match if partial_id is a prefix of or equals the file ID suffix
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
    """Move a ticket file to a new directory.

    Args:
        ticket_path: Path to the ticket file to move.
        dest_dir: Destination directory.

    Returns:
        New path to the moved ticket file.

    Raises:
        FileNotFoundError: If the ticket file doesn't exist.
    """
    if not ticket_path.exists():
        raise FileNotFoundError(f"Ticket file not found: {ticket_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    new_path = dest_dir / ticket_path.name
    ticket_path.rename(new_path)
    return new_path


def get_ticket_location(base: Path, ticket_id: str) -> Path | None:
    """Find where a ticket file is located.

    Args:
        base: Project root directory.
        ticket_id: Full or partial ticket ID.

    Returns:
        Full path to the ticket file, or None if not found.

    Raises:
        AmbiguousTicketMatch: If multiple tickets match the ID.
    """
    result = find_ticket(base, ticket_id)
    if result is None:
        return None
    return result[1]
