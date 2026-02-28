from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import branch_root, ensure_branch_layout, set_current_run


def test_cli_design_prints_path() -> None:
    """kd design should print the path to the design document."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        design_path = branch_root(base, feature) / "design.md"
        design_path.write_text("# Design: example-feature\n", encoding="utf-8")

        result = runner.invoke(cli.app, ["design"])
        assert result.exit_code == 0
        assert "design.md" in result.output


def test_cli_design_fails_when_no_design() -> None:
    """kd design should error when no design document exists."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["design"])
        assert result.exit_code == 1
        assert "No design document found" in result.output


def test_cli_design_show_renders_markdown() -> None:
    """kd design show should render the design document in the terminal."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        design_path = branch_root(base, feature) / "design.md"
        design_path.write_text("# Design: example-feature\n\nThis is the design.\n", encoding="utf-8")

        result = runner.invoke(cli.app, ["design", "show"])
        assert result.exit_code == 0
        assert "Design: example-feature" in result.output


def test_cli_design_approve_sets_flag() -> None:
    """kd design approve should set design_approved in state.json."""
    import json

    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        design_path = branch_root(base, feature) / "design.md"
        design_path.write_text("# Design: example-feature\n", encoding="utf-8")

        result = runner.invoke(cli.app, ["design", "approve"])
        assert result.exit_code == 0

        state_path = branch_root(base, feature) / "state.json"
        state = json.loads(state_path.read_text())
        assert state.get("design_approved") is True
