from __future__ import annotations

import pytest

from kingdom.breakdown import (
    ensure_breakdown_initialized,
    parse_breakdown_tickets,
    parse_breakdown_update_response,
    read_breakdown,
    write_breakdown,
)


def test_ensure_breakdown_initialized_creates_template(tmp_path) -> None:
    breakdown_path = tmp_path / "breakdown.md"
    current = ensure_breakdown_initialized(breakdown_path, feature="example-feature")

    assert "Breakdown: example-feature" in current
    assert read_breakdown(breakdown_path) == current


def test_write_breakdown_normalizes_trailing_newline(tmp_path) -> None:
    breakdown_path = tmp_path / "breakdown.md"
    write_breakdown(breakdown_path, "hello")
    assert read_breakdown(breakdown_path) == "hello\n"


def test_parse_breakdown_update_response_extracts_blocks() -> None:
    text = "\n".join(
        [
            "noise",
            "<BREAKDOWN_MD>",
            "# Breakdown: x",
            "",
            "## Goal",
            "g",
            "</BREAKDOWN_MD>",
            "<SUMMARY>Updated goal.</SUMMARY>",
        ]
    )
    update = parse_breakdown_update_response(text)

    assert update.markdown.startswith("# Breakdown: x")
    assert "## Goal" in update.markdown
    assert update.summary == "Updated goal."


def test_parse_breakdown_update_response_missing_block_raises() -> None:
    with pytest.raises(ValueError, match="Missing <BREAKDOWN_MD>"):
        parse_breakdown_update_response("<SUMMARY>ok</SUMMARY>")


def test_parse_breakdown_tickets_extracts_ids_and_fields() -> None:
    breakdown_text = "\n".join(
        [
            "# Breakdown: x",
            "",
            "## Tickets",
            "- [ ] T1: First",
            "  - Priority: 1",
            "  - Depends on: none",
            "  - Description: Hello",
            "  - Acceptance:",
            "    - [ ] A",
            "",
            "- [ ] T2: Second",
            "  - Depends on: T1",
        ]
    )
    tickets = parse_breakdown_tickets(breakdown_text)
    assert [t["breakdown_id"] for t in tickets] == ["T1", "T2"]
    assert tickets[0]["priority"] == 1
    assert tickets[0]["description"] == "Hello"
    assert tickets[0]["acceptance"] == ["A"]
    assert tickets[1]["depends_on"] == ["T1"]

