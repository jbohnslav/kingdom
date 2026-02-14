"""Helpers for drafting and iterating on `.kd/.../design.md`.

This module supports the Design phase: capturing intent, constraints, and key
decisions before converting the work into executable tickets (Breakdown phase).

Usage example:
    from pathlib import Path

    from kingdom.design import ensure_design_initialized, parse_design_update_response

    design_path = Path(".kd/runs/example/design.md")
    current = ensure_design_initialized(design_path, feature="example")

    response_text = "<DESIGN_MD>...</DESIGN_MD><SUMMARY>Updated.</SUMMARY>"
    update = parse_design_update_response(response_text)
    design_path.write_text(update.markdown, encoding="utf-8")
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kingdom.council.base import AgentResponse

DESIGN_TAG = "DESIGN_MD"
SUMMARY_TAG = "SUMMARY"


@dataclass(frozen=True)
class DesignUpdate:
    markdown: str
    summary: str


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


def write_design(design_path: Path, design_markdown: str) -> None:
    design_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = design_markdown.strip() + "\n"

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(design_path.parent),
        prefix=f".{design_path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(normalized)
        tmp_path = Path(handle.name)

    tmp_path.replace(design_path)


def build_design_council_prompt(feature: str, instruction: str, design_text: str) -> str:
    return "\n".join(
        [
            f"Feature: {feature}",
            "",
            "We are in the Design phase: clarify intent, constraints, and key decisions.",
            "",
            "Current design.md:",
            "```markdown",
            design_text.strip() or "(empty)",
            "```",
            "",
            "User instruction for this iteration:",
            instruction.strip(),
            "",
            "Task:",
            "- Propose concrete improvements to design.md.",
            "- If information is missing, list short questions to ask the user.",
            "- Prefer crisp decisions and explicit non-goals.",
            "",
            "Return a concise response with suggested edits.",
        ]
    )


def build_design_update_prompt(
    feature: str,
    instruction: str,
    design_text: str,
    responses: dict[str, AgentResponse],
    member_names: list[str] | None = None,
) -> str:
    if member_names is None:
        member_names = list(responses)

    parts: list[str] = [
        f"Feature: {feature}",
        "",
        "You are the Hand. Update the project's `design.md` in-place.",
        "",
        "Current design.md:",
        "```markdown",
        design_text.strip() or "(empty)",
        "```",
        "",
        "User instruction for this iteration:",
        instruction.strip(),
        "",
        "Council input:",
    ]

    for name in member_names:
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
            "- Output the full updated design.md content (not a diff).",
            "- Prefer minimal changes; preserve any existing good content.",
            "",
            "Return exactly two tagged blocks (any extra text is ignored):",
            f"<{DESIGN_TAG}> ... </{DESIGN_TAG}>",
            f"<{SUMMARY_TAG}> ... </{SUMMARY_TAG}>",
        ]
    )

    return "\n".join(parts)


def extract_tagged_block(text: str, tag: str) -> str:
    pattern = re.compile(
        rf"<{re.escape(tag)}>(?P<body>.*?)</{re.escape(tag)}>",
        flags=re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Missing <{tag}> block in model response.")
    return match.group("body").strip()


def parse_design_update_response(response_text: str) -> DesignUpdate:
    design_md = extract_tagged_block(response_text, DESIGN_TAG)
    summary = extract_tagged_block(response_text, SUMMARY_TAG)
    return DesignUpdate(markdown=design_md, summary=summary)
