"""Shared YAML frontmatter parsing utilities.

All kingdom files (tickets, agents, messages) use the same
``---``-delimited YAML frontmatter format.  This module provides the
single canonical implementation so that individual modules don't need
to duplicate the split + line-parse logic.
"""

from __future__ import annotations

import re


def parse_yaml_value(value: str) -> str | int | list[str] | None:
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
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Plain string
    return value


def serialize_yaml_value(value: str | int | list[str] | None) -> str:
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


# Type alias for the frontmatter dict
FrontmatterDict = dict[str, str | int | list[str] | None]


def parse_frontmatter(content: str) -> tuple[FrontmatterDict, str]:
    """Parse YAML frontmatter from a ``---``-delimited string.

    Splits the content on ``---`` delimiters and parses the key-value
    pairs in the frontmatter section using :func:`parse_yaml_value`.

    Args:
        content: Full file content beginning with ``---``.

    Returns:
        A tuple of ``(frontmatter_dict, body)`` where *body* is the
        text after the closing ``---`` (stripped of leading/trailing
        whitespace).

    Raises:
        ValueError: If the content does not start with ``---`` or lacks
            a closing ``---``.
    """
    if not content.startswith("---"):
        raise ValueError("Content must start with YAML frontmatter (---)")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter: missing closing ---")

    frontmatter = parts[1].strip()
    body = parts[2].strip()

    fm: FrontmatterDict = {}
    for line in frontmatter.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fm[key.strip()] = parse_yaml_value(value)

    return fm, body
