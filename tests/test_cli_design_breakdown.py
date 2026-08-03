from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from kingdom.cli.design import design_app
from kingdom.state import branch_root, ensure_branch_layout, set_current_run


def test_cli_design_prints_path() -> None:
    """kd design should reveal an existing design without replacing it."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        design_path = branch_root(base, feature) / "design.md"
        existing_design = "# Design: example-feature\n\nKeep this decision.\n"
        design_path.write_text(existing_design, encoding="utf-8")

        result = runner.invoke(design_app, [])
        assert result.exit_code == 0
        assert "design.md" in result.output
        assert design_path.read_text(encoding="utf-8") == existing_design


def test_cli_design_creates_optional_design_on_demand() -> None:
    """kd design should initialize the optional document when requested."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_branch_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(design_app, [])
        assert result.exit_code == 0

        design_path = branch_root(base, feature) / "design.md"
        assert design_path.exists()
        assert design_path.read_text(encoding="utf-8").startswith(f"# Design: {feature}\n")
        assert str(design_path.relative_to(base)) in result.output


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

        result = runner.invoke(design_app, ["show"])
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

        result = runner.invoke(design_app, ["approve"])
        assert result.exit_code == 0

        state_path = branch_root(base, feature) / "state.json"
        state = json.loads(state_path.read_text())
        assert state.get("design_approved") is True
