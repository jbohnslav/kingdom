"""Tests for kingdom.state module - branch name normalization and path functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    branches_root,
    check_no_legacy_runs,
    ensure_base_layout,
    ensure_branch_layout,
    find_project_root,
    normalize_branch_name,
    resolve_current_run,
    set_current_run,
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
        """Edge case: name that becomes empty after normalization raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="normalizes to empty"):
            normalize_branch_name("///")
        with pytest.raises(ValueError, match="normalizes to empty"):
            normalize_branch_name("---")

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

    def test_returns_all_paths(self, tmp_path: Path) -> None:
        """ensure_base_layout returns dict with all created paths."""
        result = ensure_base_layout(tmp_path)
        assert "state_root" in result
        assert "branches_root" in result
        assert "backlog_root" in result
        assert "archive_root" in result
        assert "worktrees_root" in result
        assert "gitignore" in result

    def test_idempotent(self, tmp_path: Path) -> None:
        """ensure_base_layout can be called multiple times safely."""
        ensure_base_layout(tmp_path)
        ensure_base_layout(tmp_path)
        assert (tmp_path / ".kd" / "branches").is_dir()

    def test_creates_gitignore_with_logs_pattern(self, tmp_path: Path) -> None:
        """ensure_base_layout creates .gitignore with **/logs/ pattern."""
        ensure_base_layout(tmp_path)
        gitignore_path = tmp_path / ".kd" / ".gitignore"
        assert gitignore_path.exists()
        content = gitignore_path.read_text()
        assert "**/logs/" in content


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

    def test_does_not_create_learnings_md(self, tmp_path: Path) -> None:
        """ensure_branch_layout no longer creates learnings.md."""
        branch_dir = ensure_branch_layout(tmp_path, "main")
        assert not (branch_dir / "learnings.md").exists()

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


class TestResolveCurrentRun:
    """Tests for resolve_current_run with git branch auto-detection."""

    def test_explicit_current_file_takes_priority(self, tmp_path: Path) -> None:
        """When .kd/current exists and points to a valid branch, use it."""
        ensure_branch_layout(tmp_path, "my-feature")
        set_current_run(tmp_path, "my-feature")
        assert resolve_current_run(tmp_path) == "my-feature"

    def test_explicit_current_file_over_git_branch(self, tmp_path: Path) -> None:
        """Explicit current file wins even if git branch differs."""
        ensure_branch_layout(tmp_path, "my-feature")
        ensure_branch_layout(tmp_path, "other-branch")
        set_current_run(tmp_path, "my-feature")
        with patch("kingdom.state.get_current_git_branch", return_value="other-branch"):
            assert resolve_current_run(tmp_path) == "my-feature"

    def test_git_branch_fallback_when_no_current_file(self, tmp_path: Path) -> None:
        """When no .kd/current exists, detect from git branch."""
        ensure_branch_layout(tmp_path, "workflow-friction")
        with patch("kingdom.state.get_current_git_branch", return_value="workflow-friction"):
            assert resolve_current_run(tmp_path) == "workflow-friction"

    def test_git_branch_normalized_match(self, tmp_path: Path) -> None:
        """Git branch name is normalized to match .kd/branches/ directory."""
        ensure_branch_layout(tmp_path, "Feature/OAuth")
        with patch("kingdom.state.get_current_git_branch", return_value="Feature/OAuth"):
            assert resolve_current_run(tmp_path) == "feature-oauth"

    def test_no_match_raises_error(self, tmp_path: Path) -> None:
        """When neither current file nor git branch matches, raise RuntimeError."""
        ensure_base_layout(tmp_path)
        with (
            patch("kingdom.state.get_current_git_branch", return_value="untracked-branch"),
            pytest.raises(RuntimeError, match="No active session"),
        ):
            resolve_current_run(tmp_path)

    def test_detached_head_raises_error(self, tmp_path: Path) -> None:
        """Detached HEAD (None from git) falls through to error."""
        ensure_base_layout(tmp_path)
        with (
            patch("kingdom.state.get_current_git_branch", return_value=None),
            pytest.raises(RuntimeError, match="No active session"),
        ):
            resolve_current_run(tmp_path)

    def test_no_git_repo_raises_error(self, tmp_path: Path) -> None:
        """Not in a git repo (None from git) falls through to error."""
        ensure_base_layout(tmp_path)
        with (
            patch("kingdom.state.get_current_git_branch", return_value=None),
            pytest.raises(RuntimeError, match="No active session"),
        ):
            resolve_current_run(tmp_path)

    def test_empty_current_file_falls_through_to_git(self, tmp_path: Path) -> None:
        """Empty .kd/current file falls through to git detection."""
        ensure_branch_layout(tmp_path, "my-feature")
        current_path = tmp_path / ".kd" / "current"
        current_path.write_text("", encoding="utf-8")
        with patch("kingdom.state.get_current_git_branch", return_value="my-feature"):
            assert resolve_current_run(tmp_path) == "my-feature"

    def test_invalid_current_session_raises_error(self, tmp_path: Path) -> None:
        """Current file points to nonexistent branch raises error when git also fails."""
        ensure_base_layout(tmp_path)
        set_current_run(tmp_path, "ghost-branch")
        with (
            patch("kingdom.state.get_current_git_branch", return_value=None),
            pytest.raises(RuntimeError, match="No active session"),
        ):
            resolve_current_run(tmp_path)

    def test_git_branch_auto_detect_returns_normalized_name(self, tmp_path: Path) -> None:
        """Git auto-detect should return normalized name, not raw git branch name."""
        ensure_branch_layout(tmp_path, "feature/my-thing")
        with patch("kingdom.state.get_current_git_branch", return_value="feature/my-thing"):
            result = resolve_current_run(tmp_path)
            # Should be normalized (feature-my-thing), not raw (feature/my-thing)
            assert result == "feature-my-thing"

    def test_stale_current_file_falls_through_to_git(self, tmp_path: Path) -> None:
        """Stale current file (points to deleted branch) should fall through to git auto-detect."""
        # Set up a current pointer to a branch that doesn't exist
        ensure_base_layout(tmp_path)
        set_current_run(tmp_path, "deleted-branch")
        # But the git branch does match a tracked branch
        ensure_branch_layout(tmp_path, "real-branch")
        with patch("kingdom.state.get_current_git_branch", return_value="real-branch"):
            result = resolve_current_run(tmp_path)
            assert result == "real-branch"


class TestFindProjectRoot:
    """Tests for find_project_root discovery logic."""

    def test_cwd_with_kd_dir(self, tmp_path: Path) -> None:
        """Finds .kd/ in cwd (fast path)."""
        (tmp_path / ".kd").mkdir()
        with patch("kingdom.state.Path.cwd", return_value=tmp_path):
            assert find_project_root() == tmp_path

    def test_walks_parent_directories(self, tmp_path: Path) -> None:
        """Finds .kd/ by walking parent directories."""
        (tmp_path / ".kd").mkdir()
        subdir = tmp_path / "src" / "kingdom"
        subdir.mkdir(parents=True)
        with patch("kingdom.state.Path.cwd", return_value=subdir):
            assert find_project_root() == tmp_path

    def test_kd_base_env_overrides(self, tmp_path: Path) -> None:
        """KD_BASE env var takes priority over cwd."""
        kd_base_dir = tmp_path / "override"
        kd_base_dir.mkdir()
        (kd_base_dir / ".kd").mkdir()
        # cwd also has .kd/ but KD_BASE should win
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        (cwd_dir / ".kd").mkdir()
        with (
            patch.dict("os.environ", {"KD_BASE": str(kd_base_dir)}),
            patch("kingdom.state.Path.cwd", return_value=cwd_dir),
        ):
            assert find_project_root() == kd_base_dir

    def test_kd_base_invalid_path_raises(self, tmp_path: Path) -> None:
        """KD_BASE pointing to a dir without .kd/ raises with the bad path."""
        bad_path = tmp_path / "no-kd-here"
        bad_path.mkdir()
        with (
            patch.dict("os.environ", {"KD_BASE": str(bad_path)}),
            pytest.raises(ValueError, match=str(bad_path)),
        ):
            find_project_root()

    def test_no_kd_anywhere_raises(self, tmp_path: Path) -> None:
        """Missing .kd/ everywhere raises with clear message."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("kingdom.state.Path.cwd", return_value=empty),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            with pytest.raises(ValueError, match="kd init"):
                find_project_root()

    def test_git_fallback(self, tmp_path: Path) -> None:
        """Falls back to git rev-parse when parent walk fails."""
        git_root = tmp_path / "repo"
        git_root.mkdir()
        (git_root / ".kd").mkdir()
        # cwd is outside the repo tree (no parents have .kd/)
        orphan = tmp_path / "orphan"
        orphan.mkdir()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("kingdom.state.Path.cwd", return_value=orphan),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = str(git_root) + "\n"
            assert find_project_root() == git_root


class TestCheckNoLegacyRuns:
    """Tests for check_no_legacy_runs guard."""

    def test_no_runs_dir_passes(self, tmp_path: Path) -> None:
        """No .kd/runs/ directory is fine."""
        ensure_base_layout(tmp_path)
        check_no_legacy_runs(tmp_path)  # should not raise

    def test_empty_runs_dir_passes(self, tmp_path: Path) -> None:
        """Empty .kd/runs/ directory is fine (leftover from old init)."""
        ensure_base_layout(tmp_path)
        (tmp_path / ".kd" / "runs").mkdir()
        check_no_legacy_runs(tmp_path)  # should not raise

    def test_non_empty_runs_dir_raises(self, tmp_path: Path) -> None:
        """Non-empty .kd/runs/ directory raises RuntimeError."""
        ensure_base_layout(tmp_path)
        runs_dir = tmp_path / ".kd" / "runs"
        runs_dir.mkdir()
        (runs_dir / "old-feature").mkdir()
        with pytest.raises(ValueError, match=r"Legacy \.kd/runs/ directory found"):
            check_no_legacy_runs(tmp_path)

    def test_find_project_root_rejects_legacy_runs(self, tmp_path: Path) -> None:
        """find_project_root raises when .kd/runs/ has content."""
        ensure_base_layout(tmp_path)
        runs_dir = tmp_path / ".kd" / "runs"
        runs_dir.mkdir()
        (runs_dir / "some-branch").mkdir()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("kingdom.state.Path.cwd", return_value=tmp_path),
            pytest.raises(ValueError, match=r"Legacy \.kd/runs/ directory found"),
        ):
            find_project_root()
