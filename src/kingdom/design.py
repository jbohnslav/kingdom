"""Initialize optional design documents with a Markdown template."""

from __future__ import annotations

from pathlib import Path


def build_design_template(feature: str) -> str:
    return (
        f"# Design: {feature}\n\n"
        "## Goal\n"
        "<what outcome are we trying to achieve?>\n\n"
        "## Context\n"
        "<what exists today / why this matters>\n\n"
        "## Requirements\n"
        "- <requirement>\n\n"
        "## Non-Goals\n"
        "- <explicitly out of scope>\n\n"
        "## Decisions\n"
        "- <decision>: <rationale>\n\n"
        "## Open Questions\n"
        "- <question>\n"
    )


def read_design(design_path: Path) -> str:
    if not design_path.exists():
        return ""
    return design_path.read_text(encoding="utf-8")


def ensure_design_initialized(design_path: Path, feature: str) -> str:
    design_path.parent.mkdir(parents=True, exist_ok=True)
    current = read_design(design_path)
    if current.strip():
        return current
    template = build_design_template(feature)
    design_path.write_text(template, encoding="utf-8")
    return template
