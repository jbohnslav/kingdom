from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import (
    branch_root,
    ensure_branch_layout,
    ensure_run_layout,
    read_json,
    set_current_run,
    state_root,
)


def test_done_marks_state_and_clears_current() -> None:
    """kd done sets status=done in state.json and clears current pointer."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0
        assert "Done: 'test-feature'" in result.output

        # Branch directory still exists (status-only, no move)
        branch_dir = branch_root(base, "test-feature")
        assert branch_dir.exists()

        # state.json updated
        state = read_json(branch_dir / "state.json")
        assert state["status"] == "done"
        assert "done_at" in state

        # Current pointer removed
        assert not (base / ".kd" / "current").exists()


def test_done_errors_without_active_run() -> None:
    """kd done fails when no current run is set."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        state_root(base).mkdir(parents=True)

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 1
        assert "No active session" in result.output


def test_done_with_explicit_feature() -> None:
    """kd done <feature> works with explicit feature argument."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "explicit-feature")

        result = runner.invoke(cli.app, ["done", "explicit-feature"])

        assert result.exit_code == 0
        assert "Done: 'explicit-feature'" in result.output

        # state.json updated in place
        state = read_json(branch_root(base, "explicit-feature") / "state.json")
        assert state["status"] == "done"


def test_done_preserves_existing_state() -> None:
    """kd done preserves existing fields in state.json."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch_dir = ensure_branch_layout(base, "test-feature")
        set_current_run(base, "test-feature")

        state_path = branch_dir / "state.json"
        existing_state = {"tickets": {"T-001": "kin-abc123"}, "peasant": {"ticket": "T-001"}}
        state_path.write_text(json.dumps(existing_state, indent=2) + "\n")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0

        state = read_json(branch_dir / "state.json")
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

        before = datetime.now(UTC)
        result = runner.invoke(cli.app, ["done"])
        after = datetime.now(UTC)

        assert result.exit_code == 0

        state = read_json(branch_root(base, "test-feature") / "state.json")
        done_at = datetime.fromisoformat(state["done_at"])

        assert before <= done_at <= after
        assert done_at.tzinfo is not None


def test_done_explicit_feature_does_not_clear_different_current() -> None:
    """kd done <other-feature> does not clear current if it's a different feature."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "current-feature")
        ensure_branch_layout(base, "other-feature")
        set_current_run(base, "current-feature")

        result = runner.invoke(cli.app, ["done", "other-feature"])

        assert result.exit_code == 0

        current_path = base / ".kd" / "current"
        assert current_path.exists()
        assert current_path.read_text().strip() == "current-feature"


def test_done_idempotent() -> None:
    """kd done on an already-done branch succeeds (idempotent)."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_branch_layout(base, "test-feature")

        # First done
        result = runner.invoke(cli.app, ["done", "test-feature"])
        assert result.exit_code == 0

        # Second done (idempotent)
        result = runner.invoke(cli.app, ["done", "test-feature"])
        assert result.exit_code == 0

        state = read_json(branch_root(base, "test-feature") / "state.json")
        assert state["status"] == "done"


def test_done_with_legacy_runs_structure() -> None:
    """kd done works with legacy .kd/runs/ structure for backwards compatibility."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        ensure_run_layout(base, "legacy-feature")
        set_current_run(base, "legacy-feature")

        result = runner.invoke(cli.app, ["done"])

        assert result.exit_code == 0
        assert "Done: 'legacy-feature'" in result.output

        # state.json updated in the legacy location
        legacy_dir = state_root(base) / "runs" / "legacy-feature"
        state = read_json(legacy_dir / "state.json")
        assert state["status"] == "done"
