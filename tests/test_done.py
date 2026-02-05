from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import (
    archive_root,
    ensure_branch_layout,
    ensure_run_layout,
    read_json,
    set_current_run,
    state_root,
)


def test_done_marks_state_and_clears_current() -> None:
    """kd done marks run as done, archives it, and clears the current pointer."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a branch-based run
        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0
        assert "Archived 'test-feature'" in result.output

        # Verify branch was moved to archive
        archive_dir = archive_root(base) / "test-feature"
        assert archive_dir.exists()

        # Verify state.json updated
        state = read_json(archive_dir / "state.json")
        assert state["status"] == "done"
        assert "done_at" in state

        # Verify original branch directory no longer exists
        assert not (base / ".kd" / "branches" / "test-feature").exists()

        # Verify current pointer removed
        assert not (base / ".kd" / "current").exists()


def test_done_errors_without_active_run() -> None:
    """kd done fails when no current run is set."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Initialize .kd but no current run
        state_root(base).mkdir(parents=True)

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 1
        assert "No active run" in result.output


def test_done_with_explicit_feature() -> None:
    """kd done <feature> works with explicit feature argument."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a branch but don't set it as current
        ensure_branch_layout(base, "explicit-feature")

        result = runner.invoke(cli.app, ["done", "explicit-feature"])

        assert result.exit_code == 0
        assert "Archived 'explicit-feature'" in result.output

        # Verify branch was moved to archive and state.json updated
        archive_dir = archive_root(base) / "explicit-feature"
        state = read_json(archive_dir / "state.json")
        assert state["status"] == "done"


def test_done_preserves_existing_state() -> None:
    """kd done preserves existing fields in state.json."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a branch with existing state
        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        # Add existing state
        state_path = branch_dir / "state.json"
        existing_state = {"tickets": {"T-001": "kin-abc123"}, "peasant": {"ticket": "T-001"}}
        state_path.write_text(json.dumps(existing_state, indent=2) + "\n")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0

        # Verify existing fields preserved in archived state
        archive_state_path = archive_root(base) / "test-feature" / "state.json"
        state = read_json(archive_state_path)
        assert state["status"] == "done"
        assert state["tickets"] == {"T-001": "kin-abc123"}
        assert state["peasant"] == {"ticket": "T-001"}


def test_done_timestamp_format() -> None:
    """kd done adds ISO UTC timestamp."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        before = datetime.now(timezone.utc)
        result = runner.invoke(cli.app, ["done"])
        after = datetime.now(timezone.utc)

        assert result.exit_code == 0

        state = read_json(archive_root(base) / "test-feature" / "state.json")
        done_at = datetime.fromisoformat(state["done_at"])

        # Verify timestamp is in valid range and UTC
        assert before <= done_at <= after
        assert done_at.tzinfo is not None


def test_done_explicit_feature_does_not_clear_different_current() -> None:
    """kd done <other-feature> does not clear current if it's a different feature."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up two branches, set one as current
        ensure_branch_layout(base, "current-feature")
        ensure_branch_layout(base, "other-feature")
        set_current_run(base, "current-feature")

        result = runner.invoke(cli.app, ["done", "other-feature"])

        assert result.exit_code == 0

        # Current pointer should still exist and point to current-feature
        current_path = base / ".kd" / "current"
        assert current_path.exists()
        assert current_path.read_text().strip() == "current-feature"


def test_done_handles_archive_collision() -> None:
    """kd done handles existing archive folder by adding timestamp suffix."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a branch
        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        # Pre-create an archive folder with same name (simulating collision)
        existing_archive = archive_root(base) / "test-feature"
        existing_archive.mkdir(parents=True)
        (existing_archive / "marker.txt").write_text("existing")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0

        # Original archive should still exist with marker
        assert (existing_archive / "marker.txt").exists()

        # New archive should have timestamp suffix
        archive_dirs = list(archive_root(base).iterdir())
        assert len(archive_dirs) == 2
        new_archive = [d for d in archive_dirs if d.name.startswith("test-feature-")][0]
        state = read_json(new_archive / "state.json")
        assert state["status"] == "done"


def test_done_with_legacy_runs_structure() -> None:
    """kd done works with legacy .kd/runs/ structure for backwards compatibility."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a legacy run (not branch)
        ensure_run_layout(base, "legacy-feature")
        set_current_run(base, "legacy-feature")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0
        assert "Archived 'legacy-feature'" in result.output

        # Verify legacy run was moved to archive
        archive_dir = archive_root(base) / "legacy-feature"
        assert archive_dir.exists()
        state = read_json(archive_dir / "state.json")
        assert state["status"] == "done"
