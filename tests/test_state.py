"""Tests for kingdom.state module - branch name normalization and path functions."""

from __future__ import annotations

from pathlib import Path

from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    branches_root,
    normalize_branch_name,
    state_root,
)


class TestNormalizeBranchName:
    """Tests for normalize_branch_name function."""

    def test_slash_to_dash(self) -> None:
        """Slashes are converted to dashes."""
        assert normalize_branch_name("feature/oauth-refresh") == "feature-oauth-refresh"

    def test_lowercase(self) -> None:
        """Uppercase letters are converted to lowercase."""
        assert normalize_branch_name("JRB/Fix-Bug") == "jrb-fix-bug"

    def test_no_double_dashes(self) -> None:
        """Multiple consecutive dashes are collapsed to single dash."""
        assert normalize_branch_name("my--branch") == "my-branch"

    def test_multiple_slashes(self) -> None:
        """Multiple slashes result in single dashes."""
        assert normalize_branch_name("a/b/c") == "a-b-c"

    def test_slash_and_double_dash_combo(self) -> None:
        """Combined slashes and double dashes are handled."""
        assert normalize_branch_name("feat//test--name") == "feat-test-name"

    def test_trailing_slash(self) -> None:
        """Trailing slashes don't result in trailing dashes."""
        assert normalize_branch_name("branch/") == "branch"

    def test_leading_slash(self) -> None:
        """Leading slashes don't result in leading dashes."""
        assert normalize_branch_name("/branch") == "branch"

    def test_non_ascii_removed(self) -> None:
        """Non-ASCII characters are removed."""
        assert normalize_branch_name("café-feature") == "cafe-feature"

    def test_unicode_normalization(self) -> None:
        """Unicode characters are normalized to ASCII equivalents."""
        assert normalize_branch_name("résumé") == "resume"

    def test_special_characters_to_dash(self) -> None:
        """Special characters are converted to dashes."""
        assert normalize_branch_name("feature_name") == "feature-name"
        assert normalize_branch_name("feature.name") == "feature-name"
        assert normalize_branch_name("feature@name") == "feature-name"

    def test_numbers_preserved(self) -> None:
        """Numbers are preserved in branch names."""
        assert normalize_branch_name("feature-123") == "feature-123"
        assert normalize_branch_name("v2/release") == "v2-release"

    def test_simple_name_unchanged(self) -> None:
        """Simple lowercase alphanumeric names are unchanged."""
        assert normalize_branch_name("main") == "main"
        assert normalize_branch_name("develop") == "develop"

    def test_empty_after_normalization(self) -> None:
        """Edge case: name that becomes empty after normalization."""
        assert normalize_branch_name("///") == ""
        assert normalize_branch_name("---") == ""

    def test_mixed_case_with_numbers(self) -> None:
        """Mixed case with numbers."""
        assert normalize_branch_name("Feature123/BugFix456") == "feature123-bugfix456"


class TestBranchesRoot:
    """Tests for branches_root function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """branches_root returns .kd/branches/ path."""
        result = branches_root(tmp_path)
        assert result == tmp_path / ".kd" / "branches"

    def test_relative_to_state_root(self, tmp_path: Path) -> None:
        """branches_root is a child of state_root."""
        result = branches_root(tmp_path)
        assert result.parent == state_root(tmp_path)


class TestBranchRoot:
    """Tests for branch_root function."""

    def test_normalizes_branch_name(self, tmp_path: Path) -> None:
        """branch_root normalizes the branch name."""
        result = branch_root(tmp_path, "feature/oauth-refresh")
        assert result == tmp_path / ".kd" / "branches" / "feature-oauth-refresh"

    def test_with_uppercase(self, tmp_path: Path) -> None:
        """branch_root handles uppercase branch names."""
        result = branch_root(tmp_path, "JRB/Fix-Bug")
        assert result == tmp_path / ".kd" / "branches" / "jrb-fix-bug"

    def test_simple_branch(self, tmp_path: Path) -> None:
        """branch_root works with simple branch names."""
        result = branch_root(tmp_path, "main")
        assert result == tmp_path / ".kd" / "branches" / "main"


class TestBacklogRoot:
    """Tests for backlog_root function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """backlog_root returns .kd/backlog/ path."""
        result = backlog_root(tmp_path)
        assert result == tmp_path / ".kd" / "backlog"

    def test_relative_to_state_root(self, tmp_path: Path) -> None:
        """backlog_root is a child of state_root."""
        result = backlog_root(tmp_path)
        assert result.parent == state_root(tmp_path)


class TestArchiveRoot:
    """Tests for archive_root function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """archive_root returns .kd/archive/ path."""
        result = archive_root(tmp_path)
        assert result == tmp_path / ".kd" / "archive"

    def test_relative_to_state_root(self, tmp_path: Path) -> None:
        """archive_root is a child of state_root."""
        result = archive_root(tmp_path)
        assert result.parent == state_root(tmp_path)
