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
