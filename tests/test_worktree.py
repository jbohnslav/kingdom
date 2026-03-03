"""Tests for kingdom.worktree module."""

from __future__ import annotations

from pathlib import Path

from kingdom.state import ensure_base_layout, ensure_branch_layout
from kingdom.worktree import design_state_path, worktree_path_for


class TestWorktreePathFor:
    def test_returns_canonical_path(self, tmp_path: Path) -> None:
        ensure_base_layout(tmp_path)
        result = worktree_path_for(tmp_path, "kin-abcd")
        assert result == tmp_path / ".kd" / "worktrees" / "kin-abcd"


class TestDesignStatePath:
    def test_returns_branch_state_json(self, tmp_path: Path) -> None:
        ensure_base_layout(tmp_path)
        ensure_branch_layout(tmp_path, "my-feature")
        result = design_state_path(tmp_path, "my-feature")
        assert result.name == "state.json"
        assert "branches" in str(result)
        assert result.exists()
