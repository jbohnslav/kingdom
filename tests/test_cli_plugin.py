"""Tests for kd plugin enable/disable/status commands."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.plugin import (
    EXTENDED_HOOK_EVENTS,
    HOOK_COMMAND,
    HOOK_CONFIG,
    HOOK_EVENTS,
    has_hook_for_event,
    is_hook_installed,
    read_settings,
    write_settings,
)

runner = CliRunner()
SUPPORTED_HOOK_EVENTS = HOOK_EVENTS + EXTENDED_HOOK_EVENTS


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestReadWriteSettings:
    def test_read_missing_file(self, tmp_path: Path) -> None:
        assert read_settings(tmp_path / "nope.json") == {}

    def test_read_existing_file(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        p.write_text('{"foo": 1}')
        assert read_settings(p) == {"foo": 1}

    def test_read_malformed_json_raises_valueerror(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        p.write_text("{bad json")
        with pytest.raises(ValueError, match="Malformed JSON"):
            read_settings(p)

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "a" / "b" / "settings.json"
        write_settings(p, {"x": 1})
        assert p.exists()
        assert json.loads(p.read_text()) == {"x": 1}

    def test_roundtrip(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        data = {"hooks": {event: [HOOK_CONFIG] for event in SUPPORTED_HOOK_EVENTS}}
        write_settings(p, data)
        assert read_settings(p) == data


class TestIsHookInstalled:
    def test_empty_settings(self) -> None:
        assert not is_hook_installed({})

    def test_no_hooks(self) -> None:
        assert not is_hook_installed({"hooks": {}})

    def test_only_user_prompt_submit_hook(self) -> None:
        settings = {"hooks": {"UserPromptSubmit": [HOOK_CONFIG]}}
        assert not is_hook_installed(settings)

    def test_only_session_start_hook(self) -> None:
        settings = {"hooks": {"SessionStart": [HOOK_CONFIG]}}
        assert not is_hook_installed(settings)

    def test_missing_one_event(self) -> None:
        settings = {
            "hooks": {"SessionStart": [HOOK_CONFIG], "UserPromptSubmit": [HOOK_CONFIG], "PostToolUse": [HOOK_CONFIG]}
        }
        assert not is_hook_installed(settings)

    def test_all_hooks_present(self) -> None:
        settings = {"hooks": {event: [HOOK_CONFIG] for event in SUPPORTED_HOOK_EVENTS}}
        assert is_hook_installed(settings)

    def test_other_hooks_only(self) -> None:
        settings = {
            "hooks": {"UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}]}
        }
        assert not is_hook_installed(settings)

    def test_kingdom_hook_among_others(self) -> None:
        other = {"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}
        settings = {"hooks": {event: [HOOK_CONFIG] for event in SUPPORTED_HOOK_EVENTS}}
        settings["hooks"]["UserPromptSubmit"] = [other, HOOK_CONFIG]
        assert is_hook_installed(settings)


class TestHasHookForEvent:
    def test_missing_event(self) -> None:
        assert not has_hook_for_event({}, "UserPromptSubmit")

    def test_present(self) -> None:
        assert has_hook_for_event({"hooks": {"UserPromptSubmit": [HOOK_CONFIG]}}, "UserPromptSubmit")


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def mock_git_root(tmp_path: Path):
    """Patch find_git_root to return tmp_path."""
    return patch("kingdom.cli.plugin.find_git_root", return_value=tmp_path)


class TestPluginEnable:
    def test_enable_creates_settings(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "enabled" in result.output

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert is_hook_installed(settings)

    def test_enable_uses_kd_hook_run_command(self, tmp_path: Path) -> None:
        """Hook command should be 'kd hook run', not a bash script path."""
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event in SUPPORTED_HOOK_EVENTS:
            hook = settings["hooks"][event][0]["hooks"][0]
            assert hook["command"] == "kd hook run"

    def test_enable_installs_all_hooks(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event in SUPPORTED_HOOK_EVENTS:
            assert has_hook_for_event(settings, event), f"Missing hook for {event}"

    def test_enable_preserves_existing_settings(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text('{"permissions": {"allow": ["Bash(git:*)"]}}')

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0

        settings = json.loads(settings_path.read_text())
        assert settings["permissions"] == {"allow": ["Bash(git:*)"]}
        assert is_hook_installed(settings)

    def test_enable_idempotent(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "already enabled" in result.output

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event in SUPPORTED_HOOK_EVENTS:
            assert len(settings["hooks"][event]) == 1

    def test_enable_adds_missing_events(self, tmp_path: Path) -> None:
        """If only some events are present, enable adds the missing ones."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({"hooks": {"UserPromptSubmit": [HOOK_CONFIG]}}))

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "enabled" in result.output

        settings = json.loads(settings_path.read_text())
        assert is_hook_installed(settings)
        assert len(settings["hooks"]["UserPromptSubmit"]) == 1
        for event in SUPPORTED_HOOK_EVENTS:
            assert has_hook_for_event(settings, event)

    def test_enable_updates_legacy_four_hook_install(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({"hooks": {event: [HOOK_CONFIG] for event in HOOK_EVENTS}}))

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "enabled" in result.output

        settings = json.loads(settings_path.read_text())
        for event in SUPPORTED_HOOK_EVENTS:
            assert has_hook_for_event(settings, event)


class TestPluginDisable:
    def test_disable_removes_hook(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])
            result = runner.invoke(app, ["plugin", "disable"])
        assert result.exit_code == 0
        assert "disabled" in result.output

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert not is_hook_installed(settings)
        assert "hooks" not in settings

    def test_disable_preserves_other_hooks(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        other_hook = {"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}
        hooks = {event: [HOOK_CONFIG] for event in SUPPORTED_HOOK_EVENTS}
        hooks["UserPromptSubmit"] = [other_hook, HOOK_CONFIG]
        settings_path.write_text(json.dumps({"hooks": hooks}))

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "disable"])
        assert result.exit_code == 0

        settings = json.loads(settings_path.read_text())
        assert "SessionStart" not in settings["hooks"]
        assert "SessionEnd" not in settings["hooks"]
        assert "PostToolUse" not in settings["hooks"]
        assert "PreCompact" not in settings["hooks"]
        assert "PostCompact" not in settings["hooks"]
        assert "SubagentStart" not in settings["hooks"]
        assert "SubagentStop" not in settings["hooks"]
        assert "Stop" not in settings["hooks"]
        assert len(settings["hooks"]["UserPromptSubmit"]) == 1
        assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "other.sh"

    def test_disable_when_not_enabled(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "disable"])
        assert result.exit_code == 0
        assert "not enabled" in result.output


class TestPluginStatus:
    def test_status_enabled(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])
            result = runner.invoke(app, ["plugin", "status"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_status_disabled(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "status"])
        assert result.exit_code == 0
        assert "disabled" in result.output


class TestHookCommand:
    def test_hook_command_is_kd_hook_run(self) -> None:
        """The hook command should be 'kd hook run', not a bash path."""
        assert HOOK_COMMAND == "kd hook run"
