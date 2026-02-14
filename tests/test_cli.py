import json
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom import cli

runner = CliRunner()


def test_doctor_all_installed() -> None:
    """Test doctor command when all CLIs are installed."""
    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch.object(cli, "check_config", return_value=(True, None)),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 0
        assert "✓" in result.output
        assert "claude" in result.output
        assert "codex" in result.output
        assert "cursor" in result.output


def test_doctor_missing_cli() -> None:
    """Test doctor command when a CLI is missing."""

    def mock_check(command: list[str]) -> tuple[bool, str | None]:
        if "codex" in command:
            return (False, "Command not found")
        return (True, None)

    with (
        patch.object(cli, "check_cli", side_effect=mock_check),
        patch.object(cli, "check_config", return_value=(True, None)),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 1
        assert "✗" in result.output
        assert "Issues found:" in result.output
        assert "npm install -g @openai/codex" in result.output


def test_doctor_json_output() -> None:
    """Test doctor command with --json flag."""
    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch.object(cli, "check_config", return_value=(True, None)),
    ):
        result = runner.invoke(cli.app, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["agents"]["claude"]["installed"] is True
        assert data["agents"]["codex"]["installed"] is True
        assert data["agents"]["cursor"]["installed"] is True
        assert data["config"]["valid"] is True


def test_doctor_json_with_missing() -> None:
    """Test doctor JSON output with missing CLI."""

    def mock_check(command: list[str]) -> tuple[bool, str | None]:
        if "codex" in command:
            return (False, "Command not found")
        return (True, None)

    with (
        patch.object(cli, "check_cli", side_effect=mock_check),
        patch.object(cli, "check_config", return_value=(True, None)),
    ):
        result = runner.invoke(cli.app, ["doctor", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["agents"]["codex"]["installed"] is False
        assert data["agents"]["codex"]["error"] == "Command not found"


def test_doctor_invalid_config() -> None:
    """Test doctor reports config validation errors."""
    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch.object(cli, "check_config", return_value=(False, "Unknown keys in config: foo")),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 1
        assert "✗" in result.output
        assert "Unknown keys in config: foo" in result.output


def test_doctor_no_config_shows_defaults(tmp_path) -> None:
    """Test doctor shows 'using defaults' when no config file exists."""
    # Create .kd dir without config.json
    (tmp_path / ".kd").mkdir()

    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch.object(cli, "check_config", return_value=(True, None)),
        patch("kingdom.state.state_root", return_value=tmp_path / ".kd"),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 0
        assert "using defaults" in result.output


def test_doctor_valid_config(tmp_path) -> None:
    """Test doctor shows config valid when config exists and is valid."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text("{}")

    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch.object(cli, "check_config", return_value=(True, None)),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 0
        assert "config.json valid" in result.output


def test_doctor_json_invalid_config() -> None:
    """Test doctor JSON output with invalid config."""
    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch.object(cli, "check_config", return_value=(False, "bad cross-reference")),
    ):
        result = runner.invoke(cli.app, ["doctor", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["config"]["valid"] is False
        assert "bad cross-reference" in data["config"]["error"]
