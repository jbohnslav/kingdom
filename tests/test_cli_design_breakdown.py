from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import ensure_run_layout, set_current_run


def test_cli_design_and_breakdown_create_templates() -> None:
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

        result = runner.invoke(cli.app, ["breakdown"])
        assert result.exit_code == 0
        breakdown_path = base / ".kd" / "runs" / feature / "breakdown.md"
        assert breakdown_path.exists()
        assert "Ticket Breakdown: example-feature" in result.output
        assert "kd tk create" in result.output


def test_cli_breakdown_does_not_embed_design_doc() -> None:
    """Breakdown prompt should reference the design doc path, not embed its contents."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        # Write a design doc with distinctive content
        design_path = base / ".kd" / "runs" / feature / "design.md"
        design_path.write_text("# Design: example-feature\n\nUNIQUE_DESIGN_CONTENT_XYZ\n", encoding="utf-8")

        result = runner.invoke(cli.app, ["breakdown"])
        assert result.exit_code == 0

        # Should reference the design doc path
        assert "design.md" in result.output
        # Should NOT embed the design doc contents
        assert "UNIQUE_DESIGN_CONTENT_XYZ" not in result.output


def test_cli_breakdown_includes_ticket_guidance() -> None:
    """Breakdown prompt should instruct agent about priorities, deps, and acceptance criteria."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["breakdown"])
        assert result.exit_code == 0
        output = result.output.lower()

        assert "priorit" in output
        assert "dependenc" in output or "kd tk dep" in result.output
        assert "acceptance criteria" in output


def test_cli_breakdown_apply_flag_is_rejected() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        result = runner.invoke(cli.app, ["breakdown", "--apply"])
        assert result.exit_code != 0
        assert "No such option" in result.output
