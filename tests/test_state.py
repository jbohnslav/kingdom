"""Tests for kingdom.state module - branch name normalization and path functions."""

from __future__ import annotations

from pathlib import Path

from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    branches_root,
    ensure_base_layout,
    ensure_branch_layout,
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


class TestEnsureBaseLayout:
    """Tests for ensure_base_layout function."""

    def test_creates_state_root(self, tmp_path: Path) -> None:
        """ensure_base_layout creates the .kd/ directory."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd").is_dir()

    def test_creates_branches_directory(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .kd/branches/ directory."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "branches").is_dir()

    def test_creates_backlog_directory(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .kd/backlog/ directory."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "backlog").is_dir()

    def test_creates_backlog_tickets_directory(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .kd/backlog/tickets/ directory."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "backlog" / "tickets").is_dir()

    def test_creates_archive_directory(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .kd/archive/ directory."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "archive").is_dir()

    def test_creates_worktrees_directory(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .kd/worktrees/ directory."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "worktrees").is_dir()

    def test_creates_runs_directory_for_backwards_compat(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .kd/runs/ for backwards compatibility."""
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "runs").is_dir()

    def test_returns_all_paths(self, tmp_path: Path) -> None:
        """ensure_base_layout returns dict with all created paths."""
        result = ensure_base_layout(tmp_path)
        assert "state_root" in result
        assert "branches_root" in result
        assert "backlog_root" in result
        assert "archive_root" in result
        assert "worktrees_root" in result
        assert "runs_root" in result
        assert "config_json" in result

    def test_idempotent(self, tmp_path: Path) -> None:
        """ensure_base_layout can be called multiple times safely."""
        ensure_base_layout(tmp_path)
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "branches").is_dir()

    def test_creates_gitignore_with_branches_pattern(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .gitignore with branches/**/logs/ pattern."""
        ensure_base_layout(tmp_path)
        gitignore_path = tmp_path / ".kd" / ".gitignore"
        assert gitignore_path.exists()
        content = gitignore_path.read_text()
        assert "branches/**/logs/" in content


class TestEnsureBranchLayout:
    """Tests for ensure_branch_layout function."""

    def test_creates_branch_directory(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates the branch directory."""
        result = ensure_branch_layout(tmp_path, "feature/test")
        assert result.is_dir()
        assert result == tmp_path / ".kd" / "branches" / "feature-test"

    def test_creates_design_md(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates design.md file."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert (branch_dir / "design.md").is_file()

    def test_creates_breakdown_md(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates breakdown.md file."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert (branch_dir / "breakdown.md").is_file()

    def test_creates_learnings_md(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates learnings.md file."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert (branch_dir / "learnings.md").is_file()

    def test_creates_tickets_directory(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates tickets/ subdirectory."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert (branch_dir / "tickets").is_dir()

    def test_creates_logs_directory(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates logs/ subdirectory."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert (branch_dir / "logs").is_dir()

    def test_creates_sessions_directory(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates sessions/ subdirectory."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert (branch_dir / "sessions").is_dir()

    def test_creates_state_json(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates state.json with empty object."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        state_path = branch_dir / "state.json"
        assert state_path.is_file()
        import json
        content = json.loads(state_path.read_text())
        assert content == {}

    def test_normalizes_branch_name(self, tmp_path: Path) -> None:
        """ensure_branch_layout normalizes branch names."""
        result = ensure_branch_layout(tmp_path, "Feature/OAuth-Refresh")
        assert result.name == "feature-oauth-refresh"

    def test_idempotent(self, tmp_path: Path) -> None:
        """ensure_branch_layout can be called multiple times safely."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        # Write some content to design.md
        (branch_dir / "design.md").write_text("# Design", encoding="utf-8")
        # Call again
        ensure_branch_layout(tmp_path, "main")
        # Content should be preserved
        assert (branch_dir / "design.md").read_text() == "# Design"

    def test_returns_branch_path(self, tmp_path: Path) -> None:
        """ensure_branch_layout returns the branch directory path."""
        result = ensure_branch_layout(tmp_path, "develop")
        assert result == tmp_path / ".kd" / "branches" / "develop"

    def test_ensures_base_layout(self, tmp_path: Path) -> None:
        """ensure_branch_layout creates base layout if not exists."""
        ensure_branch_layout(tmp_path, "main")
        # Base layout directories should exist
        assert (tmp_path / ".kd" / "branches").is_dir()
        assert (tmp_path / ".kd" / "backlog").is_dir()
        assert (tmp_path / ".kd" / "archive").is_dir()
