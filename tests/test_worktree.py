"""Tests for kingdom.worktree module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kingdom.state import ensure_base_layout, ensure_branch_layout, read_json, set_current_run, write_json
from kingdom.worktree import (
    check_uncommitted_changes,
    create_worktree,
    design_state_path,
    existing_worktree_path_for,
    is_kd_change,
    remove_worktree,
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


class TestRemoveWorktree:
    def test_requires_explicit_feature(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            remove_worktree(tmp_path, "kin-abcd", git_root=tmp_path)

    def test_uses_supplied_feature_instead_of_current_session(self, tmp_path: Path) -> None:
        import subprocess

        ensure_branch_layout(tmp_path, "feature-a")
        ensure_branch_layout(tmp_path, "feature-b")
        set_current_run(tmp_path, "feature-b")

        worktree = worktree_path_for(tmp_path, "kin-abcd", feature="feature-a")
        worktree.mkdir(parents=True)
        state_path = design_state_path(tmp_path, "feature-a")
        state = read_json(state_path)
        state["worktrees"] = {"kin-abcd": str(worktree)}
        write_json(state_path, state)

        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("kingdom.worktree.subprocess.run", return_value=result) as mock_run:
            remove_worktree(tmp_path, "kin-abcd", git_root=tmp_path, feature="feature-a")

        mock_run.assert_called_once_with(
            ["git", "worktree", "remove", "--force", str(worktree)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert read_json(state_path)["worktrees"] == {}

    @pytest.mark.parametrize(
        "failure",
        (
            json.JSONDecodeError("bad state", "{", 0),
            PermissionError("state is read-only"),
            BlockingIOError("state lock failed"),
        ),
    )
    def test_bookkeeping_failures_warn_after_removal(self, tmp_path: Path, failure: Exception) -> None:
        import subprocess

        ensure_branch_layout(tmp_path, "feature-a")
        worktree = worktree_path_for(tmp_path, "kin-abcd", feature="feature-a")
        worktree.mkdir(parents=True)
        messages: list[str] = []
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with (
            patch("kingdom.worktree.subprocess.run", return_value=result),
            patch("kingdom.worktree.update_worktree_state", side_effect=failure),
        ):
            remove_worktree(
                tmp_path,
                "kin-abcd",
                log=messages.append,
                git_root=tmp_path,
                feature="feature-a",
            )

        assert messages == [f"Warning: could not update state.json worktree map: {failure}"]


class TestCreateWorktree:
    @pytest.mark.parametrize(
        "failure",
        (
            json.JSONDecodeError("bad state", "{", 0),
            PermissionError("state is read-only"),
            BlockingIOError("state lock failed"),
        ),
    )
    def test_bookkeeping_failures_warn_after_creation(self, tmp_path: Path, failure: Exception) -> None:
        import subprocess

        ensure_branch_layout(tmp_path, "feature-a")
        set_current_run(tmp_path, "feature-a")
        messages: list[str] = []
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with (
            patch("kingdom.worktree.subprocess.run", return_value=result),
            patch("kingdom.worktree.update_worktree_state", side_effect=failure),
        ):
            worktree = create_worktree(tmp_path, "kin-abcd", log=messages.append, git_root=tmp_path)

        assert worktree == worktree_path_for(tmp_path, "kin-abcd", feature="feature-a")
        assert messages[-1] == f"Warning: could not record worktree in state.json: {failure}"


class TestDesignStatePath:
    def test_returns_branch_state_json(self, tmp_path: Path) -> None:
        ensure_base_layout(tmp_path)
        ensure_branch_layout(tmp_path, "my-feature")
        result = design_state_path(tmp_path, "my-feature")
        assert result.name == "state.json"
        assert "branches" in str(result)
        assert result.exists()
