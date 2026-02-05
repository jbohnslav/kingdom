from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import ensure_run_layout, set_current_run


def test_cli_design_creates_template() -> None:
    """Test that kd design creates a design template."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["design"])
        assert result.exit_code == 0
        design_path = base / ".kd" / "runs" / feature / "design.md"
        assert design_path.exists()
        assert "Design: example-feature" in design_path.read_text(encoding="utf-8")


def test_breakdown_requires_design_doc() -> None:
    """Test that kd breakdown fails if no design doc exists."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["breakdown"])
        assert result.exit_code == 1
        assert "No design document found" in result.output


def test_breakdown_requires_breakdown_section() -> None:
    """Test that kd breakdown fails if design has no Breakdown section."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        # Create design doc without Breakdown section
        design_path = base / ".kd" / "runs" / feature / "design.md"
        design_path.write_text("# Design\n\n## Goal\nSome goal\n", encoding="utf-8")

        result = runner.invoke(cli.app, ["breakdown"])
        assert result.exit_code == 1
        assert "no '## Breakdown' section" in result.output
