"""Helpers for `.kd/.../breakdown.md` template management."""

from __future__ import annotations

import tempfile
from pathlib import Path


def build_breakdown_template(feature: str) -> str:
    """Return a minimal `breakdown.md` template for a feature."""
    return (
        f"# Breakdown: {feature}\n\n"
        "## Design Summary\n"
        "<1-3 sentences or a link to design.md>\n\n"
        "## Goal\n"
        "<short goal>\n\n"
        "## Tickets\n"
        "- [ ] T1: <title>\n"
        "  - Priority: 2\n"
        "  - Depends on: <none|ticket ids>\n"
        "  - Description: ...\n"
        "  - Acceptance:\n"
        "    - [ ] ...\n\n"
        "## Revisions\n"
        "(append-only after dev starts)\n"
    )


def read_breakdown(breakdown_path: Path) -> str:
    """Read the breakdown file text (empty string if missing)."""
    if not breakdown_path.exists():
        return ""
    return breakdown_path.read_text(encoding="utf-8")


def ensure_breakdown_initialized(breakdown_path: Path, feature: str) -> str:
    """Ensure breakdown.md exists and is non-empty, returning the current contents."""
    breakdown_path.parent.mkdir(parents=True, exist_ok=True)
    current = read_breakdown(breakdown_path)
    if current.strip():
        return current
    template = build_breakdown_template(feature)
    breakdown_path.write_text(template, encoding="utf-8")
    return template


def write_breakdown(breakdown_path: Path, breakdown_markdown: str) -> None:
    """Write breakdown.md atomically (best-effort)."""
    breakdown_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = breakdown_markdown.strip() + "\n"

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(breakdown_path.parent),
        prefix=f".{breakdown_path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(normalized)
        tmp_path = Path(handle.name)

    tmp_path.replace(breakdown_path)
