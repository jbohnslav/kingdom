import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

import kingdom.cli as cli_mod
from kingdom.cli import app
from kingdom.cli.helpers import verbose_echo
from kingdom.cli.peasant import launch_work_tmux
from kingdom.state import ensure_base_layout, ensure_branch_layout, set_current_run

runner = CliRunner()


# ---------------------------------------------------------------------------
# Smoke tests — verify kingdom.cli.__init__ wiring
# ---------------------------------------------------------------------------


class TestCliWiring:
    """Verify sub-apps are mounted on the top-level Typer app."""

    def test_subcommands_registered(self) -> None:
        """All expected sub-apps are reachable from the top-level app."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("council", "design", "peasant", "config", "ticket", "update"):
            assert cmd in result.output, f"{cmd} not in --help output"
        # tk is a hidden alias — verify it's mounted by invoking it
        tk_result = runner.invoke(app, ["tk", "--help"])
        assert tk_result.exit_code == 0

    def test_top_level_re_exports(self) -> None:
        """kingdom.cli re-exports key symbols from submodules."""
        assert hasattr(cli_mod, "app")
        assert hasattr(cli_mod, "Council")
        assert hasattr(cli_mod, "install_skill")
        assert hasattr(cli_mod, "format_ticket_line")
        assert hasattr(cli_mod, "resolve_peasant_context")


def test_doctor_all_installed() -> None:
    """Test doctor command when all CLIs are installed."""
    with (
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.cli.check_config", return_value=(True, None)),
    ):
        result = runner.invoke(app, ["doctor"])
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
        patch("kingdom.cli.check_cli", side_effect=mock_check),
        patch("kingdom.cli.check_config", return_value=(True, None)),
    ):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "✗" in result.output
        assert "Issues found:" in result.output
        assert "npm install -g @openai/codex" in result.output


def test_doctor_json_output() -> None:
    """Test doctor command with --json flag."""
    with (
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.cli.check_config", return_value=(True, None)),
    ):
        result = runner.invoke(app, ["doctor", "--json"])
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
        patch("kingdom.cli.check_cli", side_effect=mock_check),
        patch("kingdom.cli.check_config", return_value=(True, None)),
    ):
        result = runner.invoke(app, ["doctor", "--json"])
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
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(app, ["doctor"])
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
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "using defaults" in result.output


def test_doctor_valid_config(tmp_path) -> None:
    """Test doctor shows config valid when config exists and is valid."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text("{}")

    with (
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "config.json valid" in result.output


def test_doctor_json_invalid_config(tmp_path) -> None:
    """Test doctor JSON output with invalid config is still valid JSON."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    (kd_dir / "config.json").write_text('{"peasant": {"agent": "nonexistent"}}')

    with (
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(app, ["doctor", "--json"])
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
        patch("kingdom.cli.check_cli", return_value=(True, None)),
        patch("kingdom.config.state_root", return_value=kd_dir),
        patch("kingdom.state.state_root", return_value=kd_dir),
    ):
        result = runner.invoke(app, ["doctor"])
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
        result = runner.invoke(app, ["config", "show"])
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
        result = runner.invoke(app, ["config", "show"])
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
        result = runner.invoke(app, ["config", "show"])
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
            if "council.ask.mode" in line:
                assert "broadcast" in line
                assert "default" in line
                break
        else:
            raise AssertionError("council.ask.mode not found in output")


def test_config_show_dotted_agent_name(tmp_path) -> None:
    """Agent names containing dots should show correct source annotation."""
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    config = {"agents": {"gpt.4o": {"backend": "codex", "model": "gpt-4o"}}}
    (kd_dir / "config.json").write_text(json.dumps(config))

    with patch("kingdom.config.state_root", return_value=kd_dir):
        result = runner.invoke(app, ["config", "show"])
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
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1
        assert "invalid config" in result.output
        assert "timout" in result.output


class TestNoColor:
    def test_styled_echo_strips_color_when_no_color(self) -> None:
        """styled_echo should not pass fg when NO_COLOR is set."""
        with patch.object(cli_mod, "NO_COLOR", True):
            result = runner.invoke(app, ["doctor"])
            # Output should not contain ANSI escape codes
            assert "\x1b[" not in result.output

    def test_no_color_flag_detects_env(self) -> None:
        """NO_COLOR module flag should reflect environment."""
        import importlib

        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            importlib.reload(cli_mod)
            assert cli_mod.NO_COLOR is True

        with patch.dict("os.environ", {"TERM": "dumb"}, clear=False):
            # Remove NO_COLOR if present
            import os

            env = os.environ.copy()
            env.pop("NO_COLOR", None)
            env["TERM"] = "dumb"
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(cli_mod)
                assert cli_mod.NO_COLOR is True

        # Restore normal state
        importlib.reload(cli_mod)


class TestVerboseFlag:
    """Test --verbose / -v global flag."""

    def test_verbose_flag_parsed(self) -> None:
        """--verbose stores flag in Typer context and shows debug output on config show."""
        result = runner.invoke(app, ["-v", "config", "show"])
        assert result.exit_code == 0
        assert "base:" in result.output
        assert "config path:" in result.output

    def test_no_verbose_is_silent(self) -> None:
        """Without --verbose, no debug output appears."""
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "base:" not in result.output
        assert "config path:" not in result.output

    def test_verbose_echo_silent_outside_context(self) -> None:
        """verbose_echo is a no-op when called outside a Typer context."""
        # Should not crash — just silently does nothing
        verbose_echo("should not crash")


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
            patch("kingdom.cli.resolve_peasant_context", return_value=mock_ctx),
            patch("kingdom.session.get_agent_state", return_value=mock_state),
            patch("kingdom.harness.extract_worklog", return_value="- [12:00] — Started"),
        ):
            result = runner.invoke(app, ["peasant", "watch", "t1"])

        assert result.exit_code == 0
        assert "Started" in result.output
        assert "DONE: t1" in result.output
        assert "=" * 40 in result.output


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
            patch("kingdom.cli.peasant.subprocess.run", return_value=mock_result),
            pytest.raises(ClickExit),
        ):
            launch_work_tmux(
                base=tmp_path,
                feature="test",
                ticket_id="t1",
                agent="claude",
                worktree_path=tmp_path,
                thread_id="t1-work",
                session_name="peasant-t1",
            )


class TestProjectRootDiscovery:
    """CLI commands use find_project_root to locate .kd/."""

    def test_tk_list_from_subdirectory(self, tmp_path: Path) -> None:
        """kd tk list from a subdirectory finds .kd/ at repo root."""
        ensure_base_layout(tmp_path)
        ensure_branch_layout(tmp_path, "test-branch")
        set_current_run(tmp_path, "test-branch")
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)
        with patch("kingdom.state.Path.cwd", return_value=subdir):
            result = runner.invoke(app, ["tk", "list"])
        assert result.exit_code == 0

    def test_kd_base_env_overrides_discovery(self, tmp_path: Path) -> None:
        """KD_BASE env var overrides all other discovery."""
        override = tmp_path / "override"
        override.mkdir()
        ensure_base_layout(override)
        ensure_branch_layout(override, "env-branch")
        set_current_run(override, "env-branch")
        with patch.dict(os.environ, {"KD_BASE": str(override)}):
            result = runner.invoke(app, ["tk", "list"])
        assert result.exit_code == 0

    def test_kd_base_invalid_path_shows_error(self, tmp_path: Path) -> None:
        """KD_BASE set to invalid path produces explicit error with the bad path."""
        bad = tmp_path / "bad-path"
        bad.mkdir()
        with patch.dict(os.environ, {"KD_BASE": str(bad)}):
            result = runner.invoke(app, ["tk", "list"])
        assert result.exit_code == 1
        assert "KD_BASE=" in result.output
        assert "bad-path" in result.output
        assert ".kd/" in result.output

    def test_no_kd_anywhere_shows_clear_error(self) -> None:
        """Missing .kd/ everywhere produces clear error message."""
        with runner.isolated_filesystem():
            result = runner.invoke(app, ["tk", "list"])
        assert result.exit_code == 1
        assert "kd start" in result.output or ".kd/" in result.output


# ---------------------------------------------------------------------------
# kd update
# ---------------------------------------------------------------------------


class TestUpdate:
    """Tests for the kd update command."""

    def test_update_success(self) -> None:
        """kd update upgrades CLI and refreshes skill files."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Updated kingdom-cli v0.1.0 -> v0.2.0"
        mock_result.stderr = ""

        with (
            patch("kingdom.cli.subprocess.run", return_value=mock_result),
            patch("kingdom.cli.install_skill", return_value=True) as mock_skill,
            patch("pathlib.Path.is_symlink", return_value=False),
        ):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 0
            assert "Updated kingdom-cli" in result.output
            assert "Skill files refreshed" in result.output
            mock_skill.assert_called_once()

    def test_update_upgrade_failure(self) -> None:
        """kd update reports failure when uv upgrade fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error: package not found"

        with (
            patch("kingdom.cli.subprocess.run", return_value=mock_result),
            patch("kingdom.cli.install_skill", return_value=True),
            patch("pathlib.Path.is_symlink", return_value=False),
        ):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 1
            assert "error: package not found" in result.output

    def test_update_uv_not_found(self) -> None:
        """kd update handles missing uv gracefully."""
        with (
            patch("kingdom.cli.subprocess.run", side_effect=FileNotFoundError),
            patch("kingdom.cli.install_skill", return_value=True),
            patch("pathlib.Path.is_symlink", return_value=False),
        ):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 1
            assert "uv not found" in result.output

    def test_update_skips_skill_on_dev_symlink(self) -> None:
        """kd update skips skill refresh when target is a dev symlink."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Nothing to upgrade"
        mock_result.stderr = ""

        with (
            patch("kingdom.cli.subprocess.run", return_value=mock_result),
            patch("kingdom.cli.install_skill") as mock_skill,
            patch("pathlib.Path.is_symlink", return_value=True),
        ):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 0
            assert "dev symlink" in result.output
            mock_skill.assert_not_called()

    def test_update_skill_refresh_failure(self) -> None:
        """kd update reports failure when install_skill() fails."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Nothing to upgrade"
        mock_result.stderr = ""

        with (
            patch("kingdom.cli.subprocess.run", return_value=mock_result),
            patch("kingdom.cli.install_skill", return_value=False),
            patch("pathlib.Path.is_symlink", return_value=False),
        ):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 1
            assert "Skill refresh failed" in result.output
            assert "failed" in result.output

    def test_update_appears_in_help(self) -> None:
        """kd update is visible in --help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "update" in result.output


# ---------------------------------------------------------------------------
# kd switch
# ---------------------------------------------------------------------------


class TestSwitch:
    def test_switch_updates_current(self) -> None:
        """kd switch <branch> updates .kd/current."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, "feature/alpha")
            ensure_branch_layout(base, "feature/beta")
            set_current_run(base, "feature-alpha")

            with patch("kingdom.cli.get_current_git_branch", return_value="feature/alpha"):
                result = runner.invoke(app, ["switch", "feature/beta"])
            assert result.exit_code == 0, result.output
            assert "beta" in result.output

            current = (base / ".kd" / "current").read_text().strip()
            assert current == "feature-beta"

    def test_switch_shows_ticket_counts(self) -> None:
        """kd switch prints open/closed ticket counts."""
        from datetime import UTC, datetime

        from kingdom.ticket import Ticket, write_ticket

        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, "feature/alpha")
            tickets_dir = base / ".kd" / "branches" / "feature-alpha" / "tickets"
            write_ticket(Ticket(id="t1", status="open", title="A", created=datetime.now(UTC)), tickets_dir / "t1.md")
            write_ticket(Ticket(id="t2", status="closed", title="B", created=datetime.now(UTC)), tickets_dir / "t2.md")

            with patch("kingdom.cli.get_current_git_branch", return_value="main"):
                result = runner.invoke(app, ["switch", "feature/alpha"])
            assert result.exit_code == 0
            assert "1 open" in result.output
            assert "1 closed" in result.output

    def test_switch_shows_git_mismatch(self) -> None:
        """kd switch warns when git branch doesn't match."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, "feature/alpha")

            with patch("kingdom.cli.get_current_git_branch", return_value="main"):
                result = runner.invoke(app, ["switch", "feature/alpha"])
            assert result.exit_code == 0
            assert "mismatch" in result.output

    def test_switch_no_args_lists_branches(self) -> None:
        """kd switch (no args) lists tracked branches."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, "feature/alpha")
            ensure_branch_layout(base, "feature/beta")
            set_current_run(base, "feature-alpha")

            with patch("kingdom.cli.get_current_git_branch", return_value="feature/alpha"):
                result = runner.invoke(app, ["switch"])
            assert result.exit_code == 0
            # Should list both branches
            assert "alpha" in result.output
            assert "beta" in result.output

    def test_switch_nonexistent_branch_errors(self) -> None:
        """kd switch to a non-existent branch errors."""
        with runner.isolated_filesystem():
            base = Path.cwd()
            ensure_branch_layout(base, "feature/alpha")

            result = runner.invoke(app, ["switch", "feature/nope"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_switch_appears_in_help(self) -> None:
        """kd switch is visible in --help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "switch" in result.output
