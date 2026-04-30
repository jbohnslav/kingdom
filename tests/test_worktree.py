"""Tests for kingdom.worktree module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kingdom.state import ensure_base_layout, ensure_branch_layout
from kingdom.worktree import (
    check_uncommitted_changes,
    design_state_path,
    existing_worktree_path_for,
    is_kd_change,
    sync_workflow_files,
    worktree_path_for,
)


class TestWorktreePathFor:
    def test_returns_namespaced_path_when_feature_given(self, tmp_path: Path) -> None:
        ensure_base_layout(tmp_path)
        result = worktree_path_for(tmp_path, "kin-abcd", feature="feature-test")
        assert result == tmp_path / ".kd" / "worktrees" / "feature-test" / "kin-abcd"

    def test_existing_worktree_accepts_legacy_path(self, tmp_path: Path) -> None:
        ensure_base_layout(tmp_path)
        legacy = tmp_path / ".kd" / "worktrees" / "kin-abcd"
        legacy.mkdir(parents=True)

        result = existing_worktree_path_for(tmp_path, "kin-abcd", feature="feature-test")

        assert result == legacy


class TestSyncWorkflowFiles:
    def test_copies_settings_json(self, tmp_path: Path) -> None:
        base = tmp_path / "project"
        base.mkdir()
        settings = base / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"hooks": {}}')

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        messages: list[str] = []
        sync_workflow_files(base, worktree, log=messages.append)

        dst = worktree / ".claude" / "settings.json"
        assert dst.exists()
        assert dst.read_text() == '{"hooks": {}}'
        assert any("settings.json" in m for m in messages)

    def test_skips_when_source_missing(self, tmp_path: Path) -> None:
        base = tmp_path / "project"
        base.mkdir()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        messages: list[str] = []
        sync_workflow_files(base, worktree, log=messages.append)

        assert not (worktree / ".claude" / "settings.json").exists()
        assert messages == []

    def test_skips_when_destination_already_exists(self, tmp_path: Path) -> None:
        base = tmp_path / "project"
        base.mkdir()
        settings = base / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{"source": true}')

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        dst = worktree / ".claude" / "settings.json"
        dst.parent.mkdir(parents=True)
        dst.write_text('{"existing": true}')

        sync_workflow_files(base, worktree)

        assert dst.read_text() == '{"existing": true}'


class TestCheckUncommittedChanges:
    def test_returns_changes(self, tmp_path: Path) -> None:
        import subprocess

        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=" M file.py\n?? new.txt\n")
        with patch("kingdom.worktree.subprocess.run", return_value=result):
            changes = check_uncommitted_changes(tmp_path)
        assert len(changes) == 2
        assert " M file.py" in changes

    def test_can_ignore_kd_changes(self, tmp_path: Path) -> None:
        import subprocess

        result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=" M .kd/branches/main/tickets/abcd.md\n?? .kd/runtime/state.json\n M src/app.py\n",
        )
        with patch("kingdom.worktree.subprocess.run", return_value=result):
            changes = check_uncommitted_changes(tmp_path, ignore_kd=True)
        assert changes == [" M src/app.py"]

    def test_kd_change_detects_renames_inside_kd(self) -> None:
        assert is_kd_change("R  .kd/backlog/tickets/old.md -> .kd/branches/main/tickets/old.md")

    def test_returns_empty_on_clean(self, tmp_path: Path) -> None:
        import subprocess

        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="")
        with patch("kingdom.worktree.subprocess.run", return_value=result):
            changes = check_uncommitted_changes(tmp_path)
        assert changes == []

    def test_fail_open_on_git_not_found(self, tmp_path: Path) -> None:
        with patch("kingdom.worktree.subprocess.run", side_effect=FileNotFoundError):
            changes = check_uncommitted_changes(tmp_path)
        assert changes == []

    def test_fail_open_on_git_error(self, tmp_path: Path) -> None:
        import subprocess

        result = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not a git repo")
        with patch("kingdom.worktree.subprocess.run", return_value=result):
            changes = check_uncommitted_changes(tmp_path)
        assert changes == []

    def test_fail_open_on_timeout(self, tmp_path: Path) -> None:
        import subprocess

        with patch("kingdom.worktree.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            changes = check_uncommitted_changes(tmp_path)
        assert changes == []


class TestDesignStatePath:
    def test_returns_branch_state_json(self, tmp_path: Path) -> None:
        ensure_base_layout(tmp_path)
        ensure_branch_layout(tmp_path, "my-feature")
        result = design_state_path(tmp_path, "my-feature")
        assert result.name == "state.json"
        assert "branches" in str(result)
        assert result.exists()
