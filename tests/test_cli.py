import json
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom import cli

runner = CliRunner()


def test_doctor_all_installed() -> None:
    """Test doctor command when all CLIs are installed."""
    with patch.object(cli, "_check_cli", return_value=(True, None)):
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

    with patch.object(cli, "_check_cli", side_effect=mock_check):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 1
        assert "✗" in result.output
        assert "Issues found:" in result.output
        assert "npm install -g @openai/codex" in result.output


def test_doctor_json_output() -> None:
    """Test doctor command with --json flag."""
    with patch.object(cli, "_check_cli", return_value=(True, None)):
        result = runner.invoke(cli.app, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["claude"]["installed"] is True
        assert data["codex"]["installed"] is True
        assert data["cursor"]["installed"] is True


def test_doctor_json_with_missing() -> None:
    """Test doctor JSON output with missing CLI."""

    def mock_check(command: list[str]) -> tuple[bool, str | None]:
        if "codex" in command:
            return (False, "Command not found")
        return (True, None)

    with patch.object(cli, "_check_cli", side_effect=mock_check):
        result = runner.invoke(cli.app, ["doctor", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["codex"]["installed"] is False
        assert data["codex"]["error"] == "Command not found"
