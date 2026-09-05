import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from kingdom.agent import resolve_agent
from kingdom.cli.config import AgentRuntimeCheck, check_agent_model, check_agent_runtime, get_doctor_checks
from kingdom.config import AgentDef


def completed(
    command: list[str], *, stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def test_doctor_checks_only_agents_used_by_config(tmp_path: Path) -> None:
    kd_dir = tmp_path / ".kd"
    kd_dir.mkdir()
    config = {
        "agents": {"cursor-worker": {"backend": "cursor"}},
        "council": {"members": ["cursor-worker"], "review_members": ["cursor-worker"]},
        "peasant": {"agent": "cursor-worker"},
        "lord": {"agent": "cursor-worker"},
    }
    (kd_dir / "config.json").write_text(json.dumps(config))

    with patch("kingdom.config.state_root", return_value=kd_dir):
        checks = get_doctor_checks(tmp_path)

    assert [check["name"] for check in checks] == ["cursor-worker"]


@pytest.mark.parametrize(
    ("backend", "auth_output"),
    [
        ("claude_code", '{"loggedIn": true, "email": "secret@example.com"}'),
        ("codex", "Logged in using ChatGPT"),
        ("cursor", "Logged in as secret@example.com"),
    ],
)
def test_agent_runtime_reports_version_without_account_details(backend: str, auth_output: str) -> None:
    agent = resolve_agent("worker", AgentDef(backend=backend))
    responses = [
        completed(["provider", "--version"], stdout="provider-cli 9.7\n"),
        completed(["provider", "status"], stdout=auth_output),
    ]

    with patch("kingdom.cli.config.subprocess.run", side_effect=responses):
        result = check_agent_runtime(agent)

    assert result == AgentRuntimeCheck(status="available", version="provider-cli 9.7")
    assert "secret@example.com" not in repr(result)


def test_agent_runtime_distinguishes_missing_executable_from_failed_version_probe() -> None:
    agent = resolve_agent("worker", AgentDef(backend="codex"))

    with patch("kingdom.cli.config.subprocess.run", side_effect=FileNotFoundError):
        missing = check_agent_runtime(agent)
    with patch(
        "kingdom.cli.config.subprocess.run",
        return_value=completed(["codex", "--version"], stderr="broken install", returncode=2),
    ):
        broken = check_agent_runtime(agent)

    assert missing.status == "missing"
    assert "Install Codex CLI" in missing.recovery
    assert broken.status == "version_failed"
    assert broken.error == "Version probe exited with status 2"


@pytest.mark.parametrize(
    ("backend", "auth_output"),
    [
        ("claude_code", '{"loggedIn": false, "authMethod": "none"}'),
        ("codex", "Not logged in"),
        ("cursor", "Not authenticated"),
    ],
)
def test_agent_runtime_reports_authentication_failures(backend: str, auth_output: str) -> None:
    agent = resolve_agent("worker", AgentDef(backend=backend))
    responses = [
        completed(["provider", "--version"], stdout="provider-cli 9.7"),
        completed(["provider", "status"], stdout=auth_output, returncode=int(backend != "claude_code")),
    ]

    with patch("kingdom.cli.config.subprocess.run", side_effect=responses):
        result = check_agent_runtime(agent)

    assert result.status == "authentication_failed"
    assert "kd doctor" in result.recovery


def test_agent_runtime_reports_status_probe_timeout_as_runtime_failure() -> None:
    agent = resolve_agent("worker", AgentDef(backend="cursor"))
    responses = [
        completed(["agent", "--version"], stdout="cursor-agent 9.7"),
        subprocess.TimeoutExpired(["agent", "status"], timeout=15),
    ]

    with patch("kingdom.cli.config.subprocess.run", side_effect=responses):
        result = check_agent_runtime(agent)

    assert result.status == "runtime_failed"
    assert result.error == "Authentication probe timed out"


def test_codex_catalog_accepts_new_model_ids_and_checks_effort() -> None:
    catalog = {
        "models": [
            {
                "slug": "future-model-17",
                "supported_reasoning_levels": [{"effort": "medium"}, {"effort": "high"}],
            }
        ]
    }
    agent = resolve_agent("worker", AgentDef(backend="codex", model="future-model-17", effort="high"))

    with patch(
        "kingdom.cli.config.subprocess.run",
        return_value=completed(["codex", "debug", "models"], stdout=json.dumps(catalog)),
    ):
        status, error = check_agent_model(agent)

    assert (status, error) == ("available", None)


@pytest.mark.parametrize(
    ("backend", "model", "catalog_output"),
    [
        ("codex", "retired-model", '{"models": [{"slug": "current-model"}]}'),
        ("cursor", "retired-model", "current-model\nanother-model\n"),
    ],
)
def test_provider_catalog_reports_pinned_model_drift(backend: str, model: str, catalog_output: str) -> None:
    agent = resolve_agent("worker", AgentDef(backend=backend, model=model))

    with patch(
        "kingdom.cli.config.subprocess.run",
        return_value=completed(["provider", "models"], stdout=catalog_output),
    ):
        status, error = check_agent_model(agent)

    assert status == "unavailable"
    assert model in error


@pytest.mark.parametrize("backend", ["codex", "cursor"])
def test_unavailable_catalog_discovery_is_unchecked(backend: str) -> None:
    agent = resolve_agent("worker", AgentDef(backend=backend, model="configured-model"))

    with patch(
        "kingdom.cli.config.subprocess.run",
        return_value=completed(["provider", "models"], stderr="provider changed", returncode=2),
    ):
        status, error = check_agent_model(agent)

    assert status == "unchecked"
    assert "catalog" in error.lower()


@pytest.mark.parametrize("backend", ["claude_code", "codex", "cursor"])
def test_provider_inherited_model_is_not_pinned_by_doctor(backend: str) -> None:
    agent = resolve_agent("worker", AgentDef(backend=backend))

    with patch("kingdom.cli.config.subprocess.run") as run:
        status, error = check_agent_model(agent)

    assert (status, error) == ("unchecked", None)
    run.assert_not_called()


def test_pinned_model_without_catalog_discovery_is_quietly_unchecked() -> None:
    agent = resolve_agent("claude", AgentDef(backend="claude_code", model="claude-opus-4-1"))

    with patch("kingdom.cli.config.subprocess.run") as run:
        status, error = check_agent_model(agent)

    assert (status, error) == ("unchecked", None)
    run.assert_not_called()
