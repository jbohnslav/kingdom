"""Codex plugin packaging and personal-marketplace installation tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.codex_plugin import (
    CODEX_HOOK_EVENTS,
    KINGDOM_PLUGIN_ENTRY,
    codex_plugin_install_detected,
    install_codex_plugin,
    is_codex_plugin_configured,
)
from kingdom.state import resolve_execution_context

runner = CliRunner()


def test_install_writes_manifest_skill_and_all_supported_hooks(tmp_path: Path) -> None:
    result = install_codex_plugin(tmp_path)

    plugin_root = tmp_path / "plugins" / "kingdom"
    manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text())
    hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text())

    assert result.status == "installed"
    assert manifest["name"] == "kingdom"
    assert manifest["skills"] == "./skills/"
    assert "+codex." in manifest["version"]
    assert (plugin_root / "skills" / "kingdom" / "SKILL.md").exists()
    assert set(hooks["hooks"]) == set(CODEX_HOOK_EVENTS)
    for groups in hooks["hooks"].values():
        assert groups[0]["hooks"][0]["command"] == "kd hook run --host codex"


def test_every_bundled_hook_reaches_the_shared_codex_adapter(tmp_path: Path) -> None:
    fixtures = json.loads((Path(__file__).parent / "fixtures" / "host_events.json").read_text())

    for case in fixtures["codex"]:
        payload = dict(case["payload"])
        payload["cwd"] = str(tmp_path)
        result = runner.invoke(
            app,
            ["hook", "run", "--host", "codex"],
            input=json.dumps(payload),
        )
        assert result.exit_code == 0, case["expected"]
        assert "Kingdom hook diagnostic" not in result.output, case["expected"]


def test_codex_hook_session_matches_codex_thread_context(tmp_path: Path) -> None:
    with patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-shared"}, clear=True):
        interactive = resolve_execution_context(cwd=tmp_path)
    hook = resolve_execution_context(session_id="thread-shared", host="codex", cwd=tmp_path)

    assert interactive is not None
    assert hook is not None
    assert interactive.context_id == hook.context_id


def test_install_merges_marketplace_without_touching_user_configuration(tmp_path: Path) -> None:
    marketplace_path = tmp_path / ".agents" / "plugins" / "marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    marketplace_path.write_text(
        json.dumps(
            {
                "name": "my-tools",
                "interface": {"displayName": "My tools", "userTheme": "blue"},
                "userSetting": {"keep": True},
                "plugins": [{"name": "user-plugin", "source": "./user-plugin"}],
            }
        )
    )

    result = install_codex_plugin(tmp_path)
    marketplace = json.loads(marketplace_path.read_text())

    assert result.marketplace_name == "my-tools"
    assert marketplace["interface"] == {"displayName": "My tools", "userTheme": "blue"}
    assert marketplace["userSetting"] == {"keep": True}
    assert marketplace["plugins"][0] == {"name": "user-plugin", "source": "./user-plugin"}
    assert marketplace["plugins"][1] == KINGDOM_PLUGIN_ENTRY


def test_reinstall_is_idempotent_and_preserves_unknown_plugin_files(tmp_path: Path) -> None:
    first = install_codex_plugin(tmp_path)
    plugin_root = tmp_path / "plugins" / "kingdom"
    user_file = plugin_root / "user-notes.md"
    user_file.write_text("keep me")
    marketplace_path = tmp_path / ".agents" / "plugins" / "marketplace.json"
    marketplace_before = marketplace_path.read_bytes()
    manifest_before = (plugin_root / ".codex-plugin" / "plugin.json").read_bytes()

    second = install_codex_plugin(tmp_path)

    assert first.status == "installed"
    assert second.status == "unchanged"
    assert second.changed_files == ()
    assert marketplace_path.read_bytes() == marketplace_before
    assert (plugin_root / ".codex-plugin" / "plugin.json").read_bytes() == manifest_before
    assert user_file.read_text() == "keep me"


def test_existing_kingdom_marketplace_entry_is_updated_in_place(tmp_path: Path) -> None:
    marketplace_path = tmp_path / ".agents" / "plugins" / "marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    marketplace_path.write_text(
        json.dumps(
            {
                "name": "personal",
                "plugins": [
                    {"name": "before", "source": "./before"},
                    {"name": "kingdom", "source": {"source": "local", "path": "./old"}},
                    {"name": "after", "source": "./after"},
                ],
            }
        )
    )

    install_codex_plugin(tmp_path)
    plugins = json.loads(marketplace_path.read_text())["plugins"]

    assert [entry["name"] for entry in plugins] == ["before", "kingdom", "after"]
    assert plugins[1] == KINGDOM_PLUGIN_ENTRY


def test_configured_requires_both_marketplace_entry_and_plugin_files(tmp_path: Path) -> None:
    assert not is_codex_plugin_configured(tmp_path)
    install_codex_plugin(tmp_path)
    assert is_codex_plugin_configured(tmp_path)
    (tmp_path / "plugins" / "kingdom" / "hooks" / "hooks.json").unlink()
    assert not is_codex_plugin_configured(tmp_path)
    assert codex_plugin_install_detected(tmp_path)


def test_cli_installs_and_activates_codex_plugin(tmp_path: Path) -> None:
    completed = type("Completed", (), {"returncode": 0, "stdout": "Installed kingdom", "stderr": ""})()
    with (
        patch("kingdom.cli.plugin.Path.home", return_value=tmp_path),
        patch("kingdom.cli.plugin.subprocess.run", return_value=completed) as run,
    ):
        result = runner.invoke(app, ["plugin", "install", "codex"])

    assert result.exit_code == 0
    assert "Codex plugin installed" in result.output
    assert "Preserved other marketplace entries" in result.output
    assert "new Codex task" in result.output
    assert "/hooks" in result.output
    run.assert_called_once_with(
        ["codex", "plugin", "add", "kingdom@personal"],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_reports_codex_activation_failure_without_losing_installed_files(tmp_path: Path) -> None:
    with (
        patch("kingdom.cli.plugin.Path.home", return_value=tmp_path),
        patch("kingdom.cli.plugin.subprocess.run", side_effect=FileNotFoundError),
    ):
        result = runner.invoke(app, ["plugin", "install", "codex"])

    assert result.exit_code == 1
    assert "Codex CLI was not found" in result.output
    assert (tmp_path / "plugins" / "kingdom" / ".codex-plugin" / "plugin.json").exists()


def test_cli_codex_status_is_read_only(tmp_path: Path) -> None:
    with patch("kingdom.cli.plugin.Path.home", return_value=tmp_path):
        before = runner.invoke(app, ["plugin", "status", "--host", "codex"])
        install_codex_plugin(tmp_path)
        after = runner.invoke(app, ["plugin", "status", "--host", "codex"])

    assert before.exit_code == 0
    assert "not configured" in before.output
    assert after.exit_code == 0
    assert "configured" in after.output


def test_kd_update_refreshes_an_existing_codex_plugin(tmp_path: Path) -> None:
    install_codex_plugin(tmp_path)
    upgrade = type("Completed", (), {"returncode": 0, "stdout": "Nothing to upgrade", "stderr": ""})()
    with (
        patch("kingdom.cli.Path.home", return_value=tmp_path),
        patch("kingdom.cli.subprocess.run", return_value=upgrade),
        patch("kingdom.cli.install_skill", return_value="refreshed"),
        patch("kingdom.cli.activate_codex_plugin", return_value=(True, "Installed kingdom")) as activate,
    ):
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "Codex plugin unchanged" in result.output
    assert "Codex plugin: unchanged" in result.output
    activate.assert_called_once_with("personal")
