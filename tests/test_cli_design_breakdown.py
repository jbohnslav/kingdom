from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kingdom import cli
from kingdom.council.base import AgentResponse
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


def test_breakdown_rejects_template_only_section() -> None:
    """Test that kd breakdown fails if Breakdown section only has HTML comments."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        # Create design doc with Breakdown section containing only HTML comment
        design_path = base / ".kd" / "runs" / feature / "design.md"
        design_path.write_text(
            "# Design\n\n## Goal\nSome goal\n\n## Breakdown\n" "<!--\nThis is a template placeholder.\n-->\n",
            encoding="utf-8",
        )

        result = runner.invoke(cli.app, ["breakdown"])
        assert result.exit_code == 1
        assert "no '## Breakdown' section" in result.output


def test_breakdown_with_mocked_agent() -> None:
    """Test that kd breakdown invokes the agent and displays output."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        feature = "example-feature"
        ensure_run_layout(base, feature)
        set_current_run(base, feature)

        # Create design doc with Breakdown section
        design_path = base / ".kd" / "runs" / feature / "design.md"
        design_path.write_text(
            "# Design\n\n## Goal\nSome goal\n\n## Breakdown\n- Ticket 1\n- Ticket 2\n",
            encoding="utf-8",
        )

        mock_response = AgentResponse(
            name="claude",
            text="kd ticket create 'Ticket 1'\nkd ticket create 'Ticket 2'",
            error=None,
            elapsed=1.0,
            raw="",
        )

        with patch("kingdom.cli.Council") as MockCouncil:
            mock_council = MagicMock()
            mock_council.query_single.return_value = mock_response
            MockCouncil.create.return_value = mock_council

            result = runner.invoke(cli.app, ["breakdown", "--dry-run", "--yes"])

        assert result.exit_code == 0
        assert "Planned Commands" in result.output
        mock_council.query_single.assert_called_once()
