from __future__ import annotations

from kingdom.breakdown import (
    ensure_breakdown_initialized,
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
