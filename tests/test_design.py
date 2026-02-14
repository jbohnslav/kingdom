from __future__ import annotations

import pytest

from kingdom.council.base import AgentResponse
from kingdom.design import (
    build_design_update_prompt,
    ensure_design_initialized,
    parse_design_update_response,
    read_design,
    write_design,
)


def test_ensure_design_initialized_creates_template(tmp_path) -> None:
    design_path = tmp_path / "design.md"
    current = ensure_design_initialized(design_path, feature="example-feature")

    assert "Design: example-feature" in current
    assert read_design(design_path) == current


def test_write_design_normalizes_trailing_newline(tmp_path) -> None:
    design_path = tmp_path / "design.md"
    write_design(design_path, "hello")
    assert read_design(design_path) == "hello\n"


def test_parse_design_update_response_extracts_blocks() -> None:
    text = "\n".join(
        [
            "noise",
            "<DESIGN_MD>",
            "# Design: x",
            "",
            "## Goal",
            "g",
            "</DESIGN_MD>",
            "<SUMMARY>Updated goal.</SUMMARY>",
        ]
    )
    update = parse_design_update_response(text)

    assert update.markdown.startswith("# Design: x")
    assert "## Goal" in update.markdown
    assert update.summary == "Updated goal."


def test_parse_design_update_response_missing_block_raises() -> None:
    with pytest.raises(ValueError, match="Missing <DESIGN_MD>"):
        parse_design_update_response("<SUMMARY>ok</SUMMARY>")


def test_build_design_update_prompt_custom_members() -> None:
    responses = {
        "alice": AgentResponse(name="alice", text="Alice's input", elapsed=1.0),
        "bob": AgentResponse(name="bob", text="Bob's input", elapsed=1.0),
    }
    prompt = build_design_update_prompt("feat", "do it", "# Design", responses, member_names=["alice", "bob"])
    assert "=== Alice ===" in prompt
    assert "=== Bob ===" in prompt
    assert "Alice's input" in prompt
    assert "Bob's input" in prompt


def test_build_design_update_prompt_default_members_from_responses() -> None:
    responses = {
        "claude": AgentResponse(name="claude", text="Claude says", elapsed=1.0),
    }
    prompt = build_design_update_prompt("feat", "do it", "# Design", responses)
    assert "=== Claude ===" in prompt
    assert "Claude says" in prompt
