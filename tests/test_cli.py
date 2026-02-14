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


def test_doctor_invalid_config(tmp_path) -> None:
    """Test doctor reports config errors without crashing."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text('{"council": {"timout": 123}}')

    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 1
        assert "✗" in result.output
        assert "timout" in result.output
        # Should skip CLI checks, not crash
        assert "Skipped" in result.output


def test_doctor_no_config_shows_defaults(tmp_path) -> None:
    """Test doctor shows 'using defaults' when no config file exists."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()

    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
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
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 0
        assert "config.json valid" in result.output


def test_doctor_json_invalid_config(tmp_path) -> None:
    """Test doctor JSON output with invalid config is still valid JSON."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text('{"peasant": {"agent": "nonexistent"}}')

    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(cli.app, ["doctor", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["config"]["valid"] is False
        assert "nonexistent" in data["config"]["error"]
        # CLI checks should be empty (skipped)
        assert data["agents"] == {}


def test_doctor_unknown_backend(tmp_path) -> None:
    """Test doctor catches unknown backend in config."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text('{"agents": {"test": {"backend": "foo"}}}')

    with (
        patch.object(cli, "check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(cli.app, ["doctor"])
        assert result.exit_code == 1
        assert "✗" in result.output
        assert "foo" in result.output


# -- kd config show ---


def test_config_show_defaults() -> None:
    """Test kd config show prints default config as valid JSON."""
    result = runner.invoke(cli.app, ["config", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "agents" in data
    assert "prompts" in data
    assert "council" in data
    assert "peasant" in data
    # Check defaults
    assert "claude" in data["agents"]
    assert data["peasant"]["agent"] == "claude"
    assert data["council"]["timeout"] == 600


def test_config_show_with_overrides(tmp_path) -> None:
    """Test kd config show reflects user overrides."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    config = {"council": {"timeout": 300}, "peasant": {"agent": "codex"}}
    (kd_dir / "config.json").write_text(json.dumps(config))

    with patch("kingdom.config.state_root", return_value=kd_dir):
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["council"]["timeout"] == 300
        assert data["peasant"]["agent"] == "codex"


def test_config_show_invalid_config(tmp_path) -> None:
    """Test kd config show shows clean error on invalid config."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text('{"council": {"timout": 123}}')

    with patch("kingdom.config.state_root", return_value=kd_dir):
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 1
        assert "invalid config" in result.output
        assert "timout" in result.output
