from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import (
    ensure_run_layout,
    read_json,
    set_current_run,
    state_root,
)


def test_done_marks_state_and_clears_current() -> None:
    """kd done marks run as done and clears the current pointer."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a run
        ensure_run_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0
        assert "Marked run 'test-feature' as done" in result.output

        # Verify state.json updated
        state = read_json(base / ".kd" / "runs" / "test-feature" / "state.json")
        assert state["status"] == "done"
        assert "done_at" in state

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

        # Set up a run but don't set it as current
        ensure_run_layout(base, "explicit-feature")

        result = runner.invoke(cli.app, ["done", "explicit-feature"])

        assert result.exit_code == 0
        assert "Marked run 'explicit-feature' as done" in result.output

        # Verify state.json updated
        state = read_json(base / ".kd" / "runs" / "explicit-feature" / "state.json")
        assert state["status"] == "done"


def test_done_preserves_existing_state() -> None:
    """kd done preserves existing fields in state.json."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        # Set up a run with existing state
        paths = ensure_run_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        # Add existing state
        state_path = paths["state_json"]
        existing_state = {"tickets": {"T-001": "kin-abc123"}, "peasant": {"ticket": "T-001"}}
        state_path.write_text(json.dumps(existing_state, indent=2) + "\n")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0

        # Verify existing fields preserved
        state = read_json(state_path)
        assert state["status"] == "done"
        assert state["tickets"] == {"T-001": "kin-abc123"}
        assert state["peasant"] == {"ticket": "T-001"}


def test_done_timestamp_format() -> None:
    """kd done adds ISO UTC timestamp."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_run_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        before = datetime.now(timezone.utc)
        result = runner.invoke(cli.app, ["done"])
        after = datetime.now(timezone.utc)

        assert result.exit_code == 0

        state = read_json(base / ".kd" / "runs" / "test-feature" / "state.json")
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

        # Set up two runs, set one as current
        ensure_run_layout(base, "current-feature")
        ensure_run_layout(base, "other-feature")
        set_current_run(base, "current-feature")

        result = runner.invoke(cli.app, ["done", "other-feature"])

        assert result.exit_code == 0

        # Current pointer should still exist and point to current-feature
        current_path = base / ".kd" / "current"
        assert current_path.exists()
        assert current_path.read_text().strip() == "current-feature"
