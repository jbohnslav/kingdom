from __future__ import annotations

from typer.testing import CliRunner

from kingdom import cli

runner = CliRunner()


def clear_identity_env(monkeypatch) -> None:
    monkeypatch.delenv("KD_ROLE", raising=False)
    monkeypatch.delenv("KD_AGENT_NAME", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)


def test_whoami_defaults_to_king(monkeypatch) -> None:
    clear_identity_env(monkeypatch)
    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code == 0
    assert result.output.strip() == "king"


def test_whoami_detects_hand_from_claudecode(monkeypatch) -> None:
    clear_identity_env(monkeypatch)
    monkeypatch.setenv("CLAUDECODE", "1")
    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code == 0
    assert result.output.strip() == "hand"


def test_whoami_uses_explicit_role_and_name(monkeypatch) -> None:
    clear_identity_env(monkeypatch)
    monkeypatch.setenv("KD_ROLE", "council")
    monkeypatch.setenv("KD_AGENT_NAME", "codex")
    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code == 0
    assert result.output.strip() == "council: codex"


def test_whoami_role_takes_precedence_over_claudecode(monkeypatch) -> None:
    clear_identity_env(monkeypatch)
    monkeypatch.setenv("KD_ROLE", "peasant")
    monkeypatch.setenv("CLAUDECODE", "1")
    result = runner.invoke(cli.app, ["whoami"])
    assert result.exit_code == 0
    assert result.output.strip() == "peasant"
