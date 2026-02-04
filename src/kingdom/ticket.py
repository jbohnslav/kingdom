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
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Ticket:
    """A ticket with YAML frontmatter metadata and markdown body."""

    id: str
    status: str  # open, in_progress, closed
    deps: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    created: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    type: str = "task"  # task, bug, feature
    priority: int = 2  # 0-3, 0 is highest
    assignee: str | None = None
    title: str = ""
    body: str = ""
    # Optional fields that may be present in some tickets
    tags: list[str] = field(default_factory=list)
    parent: str | None = None
    external_ref: str | None = None


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


def _parse_yaml_value(value: str) -> str | int | list[str] | None:
    """Parse a single YAML value (simple types only).

    Handles:
        - Strings (quoted or unquoted)
        - Integers
        - Lists in [item1, item2] format
        - null/empty

    Args:
        value: The raw YAML value string.

    Returns:
        Parsed Python value.
    """
    value = value.strip()

    # Handle empty/null
    if not value or value.lower() in ("null", "~"):
        return None

    # Handle lists
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        # Split by comma, strip whitespace and quotes
        items = []
        for item in inner.split(","):
            item = item.strip().strip("'\"")
            if item:
                items.append(item)
        return items

    # Handle integers
    if re.match(r"^-?\d+$", value):
        return int(value)

    # Handle quoted strings
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    # Plain string
    return value


def _serialize_yaml_value(value: str | int | list[str] | None) -> str:
    """Serialize a Python value to YAML format.

    Args:
        value: The Python value to serialize.

    Returns:
        YAML-formatted string.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        # Format as [item1, item2]
        return "[" + ", ".join(str(item) for item in value) + "]"
    # String - no quotes needed for simple values
    return str(value)


def parse_ticket(content: str) -> Ticket:
    """Parse ticket content from YAML frontmatter + markdown body.

    Args:
        content: The full ticket file content.

    Returns:
        A Ticket instance.

    Raises:
        ValueError: If the content doesn't have valid frontmatter.
    """
    # Split frontmatter from body
    if not content.startswith("---"):
        raise ValueError("Ticket must start with YAML frontmatter (---)")

    # Find the closing ---
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter: missing closing ---")

    frontmatter = parts[1].strip()
    body_content = parts[2].strip()

    # Parse frontmatter into dict
    frontmatter_dict: dict[str, str | int | list[str] | None] = {}
    for line in frontmatter.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        frontmatter_dict[key] = _parse_yaml_value(value)

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
        created = datetime.now(timezone.utc)

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
        priority=int(frontmatter_dict.get("priority", 2)) if frontmatter_dict.get("priority") else 2,
        assignee=str(frontmatter_dict.get("assignee")) if frontmatter_dict.get("assignee") else None,
        title=title,
        body=body,
        tags=tags if isinstance(tags, list) else [],
        parent=str(frontmatter_dict.get("parent")) if frontmatter_dict.get("parent") else None,
        external_ref=(
            str(frontmatter_dict.get("external-ref"))
            if frontmatter_dict.get("external-ref")
            else None
        ),
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
    lines.append(f"deps: {_serialize_yaml_value(ticket.deps)}")
    lines.append(f"links: {_serialize_yaml_value(ticket.links)}")

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
        lines.append(f"tags: {_serialize_yaml_value(ticket.tags)}")

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
