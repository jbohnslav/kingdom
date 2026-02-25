import json
import subprocess
from unittest.mock import MagicMock, patch

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


def test_config_show_defaults(tmp_path) -> None:
    """Test kd config show prints all-default config with source annotations."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    # No config.json — everything should be "default"
    with patch("kingdom.config.state_root", return_value=kd_dir):
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 0
        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        assert len(lines) > 0
        for line in lines:
            assert "default" in line
        # Spot-check a few known defaults
        assert any("peasant.agent" in ln and "claude" in ln for ln in lines)
        assert any("council.timeout" in ln and "600" in ln for ln in lines)


def test_config_show_with_overrides(tmp_path) -> None:
    """Test kd config show reflects user overrides."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    config = {"council": {"timeout": 300}, "peasant": {"agent": "codex"}}
    (kd_dir / "config.json").write_text(json.dumps(config))

    with (
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.cli.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 0
        assert "council.timeout" in result.output
        assert "300" in result.output
        assert "config" in result.output  # source annotation for overridden value


def test_config_show_indicates_sources(tmp_path) -> None:
    """Test kd config show annotates each value with its source."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    config = {"council": {"timeout": 300}}
    (kd_dir / "config.json").write_text(json.dumps(config))

    with patch("kingdom.config.state_root", return_value=kd_dir):
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 0
        # Overridden value shows "config" source
        for line in result.output.splitlines():
            if "council.timeout" in line:
                assert "300" in line
                assert "config" in line
                break
        else:
            raise AssertionError("council.timeout not found in output")
        # Default value shows "default" source
        for line in result.output.splitlines():
            if "council.mode" in line:
                assert "broadcast" in line
                assert "default" in line
                break
        else:
            raise AssertionError("council.mode not found in output")


def test_config_show_dotted_agent_name(tmp_path) -> None:
    """Agent names containing dots should show correct source annotation."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    config = {"agents": {"gpt.4o": {"backend": "codex", "model": "gpt-4o"}}}
    (kd_dir / "config.json").write_text(json.dumps(config))

    with patch("kingdom.config.state_root", return_value=kd_dir):
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 0
        for line in result.output.splitlines():
            if "gpt.4o" in line and "backend" in line:
                assert "config" in line, f"Expected (config) source but got: {line}"
                break
        else:
            raise AssertionError("agents.gpt.4o.backend not found in output")


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


class TestSetupSkill:
    def test_creates_symlink(self, tmp_path) -> None:
        # Create skills directory in fake project
        skill_dir = tmp_path / "skills" / "kingdom"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Skill")

        claude_skills = tmp_path / ".claude_skills"

        with (
            patch("kingdom.cli.Path.cwd", return_value=tmp_path),
            patch("kingdom.cli.Path.home", return_value=tmp_path),
        ):
            # Patch the home directory to use tmp_path
            claude_skills / "kingdom"
            with patch.object(cli, "Path"):
                # This is complex to mock; use runner with isolated fs instead
                pass

        # Simpler: test via runner.isolated_filesystem
        with runner.isolated_filesystem():
            from pathlib import Path as P

            base = P.cwd()
            (base / "skills" / "kingdom").mkdir(parents=True)
            (base / "skills" / "kingdom" / "SKILL.md").write_text("# Skill")

            fake_home = base / "fakehome"
            fake_home.mkdir()

            with (
                patch("kingdom.cli.Path.home", return_value=fake_home),
            ):
                result = runner.invoke(cli.app, ["setup-skill"])

            assert result.exit_code == 0, result.output
            assert "Linked" in result.output

            link = fake_home / ".claude" / "skills" / "kingdom"
            assert link.is_symlink()
            assert link.resolve() == (base / "skills" / "kingdom").resolve()

    def test_already_linked(self) -> None:
        with runner.isolated_filesystem():
            from pathlib import Path as P

            base = P.cwd()
            (base / "skills" / "kingdom").mkdir(parents=True)
            (base / "skills" / "kingdom" / "SKILL.md").write_text("# Skill")

            fake_home = base / "fakehome"
            target = fake_home / ".claude" / "skills" / "kingdom"
            target.parent.mkdir(parents=True)
            target.symlink_to(base / "skills" / "kingdom")

            with patch("kingdom.cli.Path.home", return_value=fake_home):
                result = runner.invoke(cli.app, ["setup-skill"])

            assert result.exit_code == 0, result.output
            assert "Already linked" in result.output

    def test_no_skill_dir(self) -> None:
        with runner.isolated_filesystem():
            from pathlib import Path as P

            fake_home = P.cwd() / "fakehome"
            fake_home.mkdir()

            with patch("kingdom.cli.Path.home", return_value=fake_home):
                result = runner.invoke(cli.app, ["setup-skill"])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_updates_stale_symlink(self) -> None:
        with runner.isolated_filesystem():
            from pathlib import Path as P

            base = P.cwd()
            (base / "skills" / "kingdom").mkdir(parents=True)
            (base / "skills" / "kingdom" / "SKILL.md").write_text("# Skill")

            fake_home = base / "fakehome"
            target = fake_home / ".claude" / "skills" / "kingdom"
            target.parent.mkdir(parents=True)
            target.symlink_to("/nonexistent/old/path")

            with patch("kingdom.cli.Path.home", return_value=fake_home):
                result = runner.invoke(cli.app, ["setup-skill"])

            assert result.exit_code == 0, result.output
            assert "Updating" in result.output
            assert target.resolve() == (base / "skills" / "kingdom").resolve()

    def test_works_from_subdirectory(self) -> None:
        """setup-skill should resolve repo root via git, not cwd."""
        with runner.isolated_filesystem():
            from pathlib import Path as P

            base = P.cwd()
            (base / "skills" / "kingdom").mkdir(parents=True)
            (base / "skills" / "kingdom" / "SKILL.md").write_text("# Skill")
            subdir = base / "src" / "deep"
            subdir.mkdir(parents=True)

            fake_home = base / "fakehome"
            fake_home.mkdir()

            original_run = subprocess.run

            def mock_run(cmd, **kwargs):
                if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
                    return MagicMock(returncode=0, stdout=str(base) + "\n")
                return original_run(cmd, **kwargs)

            with (
                patch("kingdom.cli.Path.home", return_value=fake_home),
                patch("kingdom.cli.subprocess.run", side_effect=mock_run),
                patch("kingdom.cli.Path.cwd", return_value=subdir),
            ):
                result = runner.invoke(cli.app, ["setup-skill"])

            assert result.exit_code == 0, result.output
            assert "Linked" in result.output
            link = fake_home / ".claude" / "skills" / "kingdom"
            assert link.is_symlink()
            assert link.resolve() == (base / "skills" / "kingdom").resolve()


class TestNoColor:
    def test_styled_echo_strips_color_when_no_color(self) -> None:
        """styled_echo should not pass fg when NO_COLOR is set."""
        with patch.object(cli, "NO_COLOR", True):
            result = runner.invoke(cli.app, ["doctor"])
            # Output should not contain ANSI escape codes
            assert "\x1b[" not in result.output

    def test_no_color_flag_detects_env(self) -> None:
        """NO_COLOR module flag should reflect environment."""
        import importlib

        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            importlib.reload(cli)
            assert cli.NO_COLOR is True

        with patch.dict("os.environ", {"TERM": "dumb"}, clear=False):
            # Remove NO_COLOR if present
            import os

            env = os.environ.copy()
            env.pop("NO_COLOR", None)
            env["TERM"] = "dumb"
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(cli)
                assert cli.NO_COLOR is True

        # Restore normal state
        importlib.reload(cli)


class TestVerboseFlag:
    """Test --verbose / -v global flag."""

    def test_verbose_flag_accessible(self) -> None:
        """VERBOSE module-level flag exists and defaults to False."""
        assert hasattr(cli, "VERBOSE")
        assert cli.VERBOSE is False

    def test_verbose_flag_parsed(self) -> None:
        """--verbose sets the module flag and shows debug output on config show."""
        result = runner.invoke(cli.app, ["-v", "config", "show"])
        assert result.exit_code == 0
        assert "base:" in result.output
        assert "config path:" in result.output

    def test_no_verbose_is_silent(self) -> None:
        """Without --verbose, no debug output appears."""
        result = runner.invoke(cli.app, ["config", "show"])
        assert result.exit_code == 0
        assert "base:" not in result.output
        assert "config path:" not in result.output

    def test_verbose_echo_helper(self) -> None:
        """verbose_echo only prints when VERBOSE is True."""
        from io import StringIO

        from rich.console import Console

        buf = StringIO()
        cli.VERBOSE = False
        # verbose_echo writes to error_console; patch it
        original = cli.error_console
        cli.error_console = Console(file=buf, no_color=True)
        try:
            cli.verbose_echo("should not appear")
            assert buf.getvalue() == ""

            cli.VERBOSE = True
            cli.verbose_echo("should appear")
            assert "should appear" in buf.getvalue()
        finally:
            cli.VERBOSE = False
            cli.error_console = original


class TestPeasantWatch:
    """Tests for the kd peasant watch command."""

    def test_watch_exits_on_terminal_status(self, tmp_path) -> None:
        """Watch exits when peasant reaches a terminal status."""
        from kingdom.session import AgentState

        # Create a ticket with a worklog
        ticket_path = tmp_path / "ticket.md"
        ticket_path.write_text(
            "---\nid: t1\nstatus: in_progress\n---\n# Test\n\n## Worklog\n\n- [12:00] — Started\n",
            encoding="utf-8",
        )

        mock_ctx = MagicMock()
        mock_ctx.base = tmp_path
        mock_ctx.feature = "test"
        mock_ctx.full_ticket_id = "t1"
        mock_ctx.ticket_path = ticket_path

        mock_state = AgentState(name="peasant-t1", status="done")

        with (
            patch.object(cli, "resolve_peasant_context", return_value=mock_ctx),
            patch("kingdom.session.get_agent_state", return_value=mock_state),
            patch("kingdom.harness.extract_worklog", return_value="- [12:00] — Started"),
        ):
            result = runner.invoke(cli.app, ["peasant", "watch", "t1"])

        assert result.exit_code == 0
        assert "Started" in result.output
        assert "finished: done" in result.output


class TestPeasantTmux:
    """Tests for the kd peasant start --tmux flag."""

    def test_tmux_errors_when_not_running(self, tmp_path) -> None:
        """--tmux should error if tmux is not running."""
        import pytest
        from click.exceptions import Exit as ClickExit

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "no server running"

        with (
            patch("kingdom.cli.subprocess.run", return_value=mock_result),
            pytest.raises(ClickExit),
        ):
            cli.launch_work_tmux(
                base=tmp_path,
                feature="test",
                ticket_id="t1",
                agent="claude",
                worktree_path=tmp_path,
                thread_id="t1-work",
                session_name="peasant-t1",
            )
