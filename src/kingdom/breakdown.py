"""Helpers for drafting and iterating on `.kd/.../breakdown.md`.

This module is used by the Hand interactive chat to keep the breakdown file
updated in-place during the breakdown phase.

Usage example:
    from pathlib import Path

    from kingdom.breakdown import ensure_breakdown_initialized, parse_breakdown_update_response

    breakdown_path = Path(".kd/runs/example/breakdown.md")
    current = ensure_breakdown_initialized(breakdown_path, feature="example")

    response_text = "<BREAKDOWN_MD>...</BREAKDOWN_MD><SUMMARY>Updated.</SUMMARY>"
    update = parse_breakdown_update_response(response_text)
    breakdown_path.write_text(update.markdown, encoding="utf-8")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from typing import Any

from kingdom.council.base import AgentResponse


BREAKDOWN_TAG = "BREAKDOWN_MD"
SUMMARY_TAG = "SUMMARY"


@dataclass(frozen=True)
class BreakdownUpdate:
    """A parsed breakdown update from the Hand model."""

    markdown: str
    summary: str


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


def build_breakdown_council_prompt(
    feature: str,
    instruction: str,
    design_text: str,
    breakdown_text: str,
) -> str:
    """Prompt council members for breakdown review and concrete improvements."""
    return "\n".join(
        [
            f"Feature: {feature}",
            "",
            "We are in the Breakdown phase: convert design into executable tickets.",
            "",
            "Current design.md:",
            "```markdown",
            design_text.strip() or "(empty)",
            "```",
            "",
            "Current breakdown.md:",
            "```markdown",
            breakdown_text.strip() or "(empty)",
            "```",
            "",
            "User instruction for this iteration:",
            instruction.strip(),
            "",
            "Task:",
            "- Propose concrete improvements to the breakdown.md content.",
            "- Keep the existing structure and ticket ID scheme (T1, T2, ...).",
            "- If information is missing, list short questions to ask the user.",
            "",
            "Return a concise response with suggested edits.",
        ]
    )


def build_breakdown_update_prompt(
    feature: str,
    instruction: str,
    design_text: str,
    breakdown_text: str,
    responses: dict[str, AgentResponse],
) -> str:
    """Build a prompt that asks the Hand model to update breakdown.md."""
    parts: list[str] = [
        f"Feature: {feature}",
        "",
        "You are the Hand. Update the project's `breakdown.md` in-place.",
        "",
        "Current design.md (source of truth for intent/decisions):",
        "```markdown",
        design_text.strip() or "(empty)",
        "```",
        "",
        "Current breakdown.md (tickets/deps/acceptance):",
        "```markdown",
        breakdown_text.strip() or "(empty)",
        "```",
        "",
        "User instruction for this iteration:",
        instruction.strip(),
        "",
        "Council input:",
    ]

    for name in ["claude", "codex", "agent"]:
        resp = responses.get(name)
        parts.append(f"\n=== {name.title()} ===")
        if resp and resp.text:
            parts.append(resp.text.strip())
        elif resp and resp.error:
            parts.append(f"[Failed: {resp.error}]")
        else:
            parts.append("[No response]")

    parts.extend(
        [
            "",
            "Rules:",
            "- Output the full updated breakdown.md content (not a diff).",
            "- Keep `## Revisions` section present, even if empty.",
            "- Prefer minimal changes; preserve any existing good content.",
            "",
            f"Return exactly two tagged blocks (any extra text is ignored):",
            f"<{BREAKDOWN_TAG}> ... </{BREAKDOWN_TAG}>",
            f"<{SUMMARY_TAG}> ... </{SUMMARY_TAG}>",
        ]
    )

    return "\n".join(parts)


def extract_tagged_block(text: str, tag: str) -> str:
    """Extract a single tagged block like `<TAG>...</TAG>` from text."""
    pattern = re.compile(
        rf"<{re.escape(tag)}>(?P<body>.*?)</{re.escape(tag)}>",
        flags=re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Missing <{tag}> block in model response.")
    return match.group("body").strip()


def parse_breakdown_update_response(response_text: str) -> BreakdownUpdate:
    """Parse an updated breakdown and summary from a model response."""
    breakdown_md = extract_tagged_block(response_text, BREAKDOWN_TAG)
    summary = extract_tagged_block(response_text, SUMMARY_TAG)
    return BreakdownUpdate(markdown=breakdown_md, summary=summary)


def parse_breakdown_tickets(breakdown_text: str) -> list[dict[str, Any]]:
    """Parse `## Tickets` in breakdown.md into structured ticket dicts.

    Expected format (example):
        ## Tickets
        - [ ] T1: Do thing
          - Priority: 2
          - Depends on: none
          - Description: ...
          - Acceptance:
            - [ ] ...
    """
    lines = breakdown_text.splitlines()
    in_tickets = False
    tickets: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    collecting_acceptance = False

    header_re = re.compile(r"^- \[[ xX]\] (?P<id>[^:]+): (?P<title>.+)$")

    for line in lines:
        if line.startswith("## "):
            in_tickets = line.strip() == "## Tickets"
            collecting_acceptance = False
            current = None
            continue

        if not in_tickets:
            continue

        match = header_re.match(line)
        if match:
            current = {
                "breakdown_id": match.group("id").strip(),
                "title": match.group("title").strip(),
                "priority": 2,
                "depends_on": [],
                "description": "",
                "acceptance": [],
            }
            tickets.append(current)
            collecting_acceptance = False
            continue

        if current is None:
            continue

        if line.startswith("  - "):
            collecting_acceptance = False
            key, _, value = line[4:].partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "priority":
                if value.isdigit():
                    current["priority"] = int(value)
            elif key == "depends on":
                if value.lower() != "none":
                    deps = [item.strip() for item in value.split(",") if item.strip()]
                    current["depends_on"] = deps
            elif key == "description":
                current["description"] = value
            elif key == "acceptance":
                collecting_acceptance = True
            continue

        if collecting_acceptance and line.strip().startswith("-"):
            item = line.strip()
            item = item.removeprefix("- [ ]").removeprefix("-").strip()
            current["acceptance"].append(item)

    return tickets
