from __future__ import annotations

from kingdom.design import (
    ensure_design_initialized,
    read_design,
)


def test_ensure_design_initialized_creates_template(tmp_path) -> None:
    design_path = tmp_path / "design.md"
    current = ensure_design_initialized(design_path, feature="example-feature")

    assert "Design: example-feature" in current
    assert read_design(design_path) == current
