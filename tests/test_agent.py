"""Tests for agent configuration and command building."""

import pytest

from kingdom.agent import (
    BACKEND_DEFAULTS,
    AgentConfig,
    build_command,
    parse_claude_response,
    parse_codex_response,
    parse_cursor_response,
    parse_response,
    resolve_agent,
    resolve_all_agents,
)
from kingdom.config import DEFAULT_AGENTS, AgentDef


class TestBackendDefaults:
    def test_all_backends_defined(self) -> None:
        assert set(BACKEND_DEFAULTS) == {"claude_code", "codex", "cursor"}

    def test_claude_code_defaults(self) -> None:
        d = BACKEND_DEFAULTS["claude_code"]
        assert "claude" in d["cli"]
        assert d["resume_flag"] == "--resume"
        assert d["version_command"] == "claude --version"
        assert d["install_hint"]

    def test_codex_defaults(self) -> None:
        d = BACKEND_DEFAULTS["codex"]
        assert "codex" in d["cli"]
        assert d["resume_flag"] == "resume"
        assert d["version_command"] == "codex --version"

    def test_cursor_defaults(self) -> None:
        d = BACKEND_DEFAULTS["cursor"]
        assert "agent" in d["cli"]
        assert d["resume_flag"] == "--resume"
        assert d["version_command"] == "agent --version"


class TestResolveAgent:
    def test_resolve_claude(self) -> None:
        config = resolve_agent("claude", AgentDef(backend="claude_code"))
        assert config.name == "claude"
        assert config.backend == "claude_code"
        assert "claude" in config.cli
        assert config.resume_flag == "--resume"

    def test_resolve_with_model(self) -> None:
        config = resolve_agent("claude", AgentDef(backend="claude_code", model="opus-4-6"))
        assert config.model == "opus-4-6"

    def test_resolve_with_extra_flags(self) -> None:
        config = resolve_agent("claude", AgentDef(backend="claude_code", extra_flags=["--verbose"]))
        assert config.extra_flags == ["--verbose"]

    def test_resolve_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend 'fake'"):
            resolve_agent("test", AgentDef(backend="fake"))

    def test_resolve_all_defaults(self) -> None:
        configs = resolve_all_agents(DEFAULT_AGENTS)
        assert set(configs) == {"claude", "codex", "cursor"}
        assert configs["claude"].backend == "claude_code"
        assert configs["codex"].backend == "codex"
        assert configs["cursor"].backend == "cursor"


class TestAgentConfig:
    def test_dataclass_fields(self) -> None:
        config = AgentConfig(
            name="test",
            backend="claude_code",
            cli="test --flag",
            resume_flag="--resume",
        )
        assert config.name == "test"
        assert config.backend == "claude_code"
        assert config.cli == "test --flag"
        assert config.resume_flag == "--resume"
        assert config.version_command == ""
        assert config.install_hint == ""
        assert config.model == ""
        assert config.extra_flags == []

    def test_optional_fields(self) -> None:
        config = AgentConfig(
            name="test",
            backend="claude_code",
            cli="test --flag",
            resume_flag="--resume",
            version_command="test --version",
            install_hint="Install test",
            model="opus-4-6",
            extra_flags=["--verbose"],
        )
        assert config.version_command == "test --version"
        assert config.install_hint == "Install test"
        assert config.model == "opus-4-6"
        assert config.extra_flags == ["--verbose"]


def make_config(name: str) -> AgentConfig:
    """Resolve a default agent into an AgentConfig for tests."""
    return resolve_agent(name, DEFAULT_AGENTS[name])


class TestBuildCommand:
    def test_claude_without_session(self) -> None:
        cmd = build_command(make_config("claude"), "hello world")
        assert cmd == [
            "claude",
            "--dangerously-skip-permissions",
            "--print",
            "--output-format",
            "json",
            "-p",
            "hello world",
        ]

    def test_claude_with_session(self) -> None:
        cmd = build_command(make_config("claude"), "hello", session_id="abc123")
        assert cmd == [
            "claude",
            "--dangerously-skip-permissions",
            "--print",
            "--output-format",
            "json",
            "--resume",
            "abc123",
            "-p",
            "hello",
        ]

    def test_codex_without_session(self) -> None:
        cmd = build_command(make_config("codex"), "hello world")
        assert cmd == [
            "codex",
            "--dangerously-bypass-approvals-and-sandbox",
            "exec",
            "--json",
            "hello world",
        ]

    def test_codex_with_session(self) -> None:
        cmd = build_command(make_config("codex"), "hello", session_id="thread-123")
        assert cmd == [
            "codex",
            "--dangerously-bypass-approvals-and-sandbox",
            "exec",
            "resume",
            "thread-123",
            "--json",
            "hello",
        ]

    def test_cursor_without_session(self) -> None:
        cmd = build_command(make_config("cursor"), "hello world")
        assert cmd == [
            "agent",
            "--force",
            "--sandbox",
            "disabled",
            "--print",
            "--output-format",
            "json",
            "hello world",
        ]

    def test_cursor_with_session(self) -> None:
        cmd = build_command(make_config("cursor"), "hello", session_id="conv-456")
        assert cmd == [
            "agent",
            "--force",
            "--sandbox",
            "disabled",
            "--print",
            "--output-format",
            "json",
            "hello",
            "--resume",
            "conv-456",
        ]

    def test_unknown_backend_raises(self) -> None:
        config = AgentConfig(name="bad", backend="unknown", cli="bad", resume_flag="")
        with pytest.raises(ValueError, match="Unknown backend"):
            build_command(config, "test")

    def test_codex_missing_exec_raises(self) -> None:
        config = AgentConfig(name="codex", backend="codex", cli="codex --json", resume_flag="resume")
        with pytest.raises(ValueError, match="must contain 'exec'"):
            build_command(config, "hello", session_id="thread-1")


class TestBuildCommandModel:
    def test_claude_with_model(self) -> None:
        config = resolve_agent("claude", AgentDef(backend="claude_code", model="opus-4-6"))
        cmd = build_command(config, "hello")
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "opus-4-6"

    def test_codex_with_model(self) -> None:
        config = resolve_agent("codex", AgentDef(backend="codex", model="o3"))
        cmd = build_command(config, "hello")
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "o3"

    def test_cursor_with_model(self) -> None:
        config = resolve_agent("cursor", AgentDef(backend="cursor", model="llama-3.1"))
        cmd = build_command(config, "hello")
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "llama-3.1"

    def test_no_model_no_flag(self) -> None:
        config = make_config("claude")
        cmd = build_command(config, "hello")
        assert "--model" not in cmd


class TestBuildCommandExtraFlags:
    def test_claude_extra_flags(self) -> None:
        config = resolve_agent("claude", AgentDef(backend="claude_code", extra_flags=["--verbose", "--no-cache"]))
        cmd = build_command(config, "hello")
        assert "--verbose" in cmd
        assert "--no-cache" in cmd
        # Extra flags should come before the prompt
        prompt_idx = cmd.index("-p")
        verbose_idx = cmd.index("--verbose")
        assert verbose_idx < prompt_idx

    def test_codex_extra_flags(self) -> None:
        config = resolve_agent("codex", AgentDef(backend="codex", extra_flags=["--debug"]))
        cmd = build_command(config, "hello")
        assert "--debug" in cmd

    def test_cursor_extra_flags(self) -> None:
        config = resolve_agent("cursor", AgentDef(backend="cursor", extra_flags=["--debug"]))
        cmd = build_command(config, "hello")
        assert "--debug" in cmd
        # Extra flags before prompt (positional)
        prompt_idx = cmd.index("hello")
        debug_idx = cmd.index("--debug")
        assert debug_idx < prompt_idx


class TestBuildCommandSkipPermissions:
    def test_claude_skip_permissions_false(self) -> None:
        cmd = build_command(make_config("claude"), "hello world", skip_permissions=False)
        assert "--dangerously-skip-permissions" not in cmd
        assert "--allowedTools" in cmd
        assert "Read" in cmd
        assert "Glob" in cmd
        assert "Grep" in cmd
        assert "Edit" not in cmd
        assert "Write" not in cmd
        assert "Bash" in cmd

    def test_codex_skip_permissions_false(self) -> None:
        cmd = build_command(make_config("codex"), "hello world", skip_permissions=False)
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
        assert "disk-full-read-access" in " ".join(cmd)

    def test_cursor_skip_permissions_false(self) -> None:
        cmd = build_command(make_config("cursor"), "hello world", skip_permissions=False)
        assert "--force" not in cmd
        assert "--sandbox" not in cmd
        assert "disabled" not in cmd
        assert "--mode" in cmd
        assert "ask" in cmd

    def test_claude_skip_permissions_true_is_default(self) -> None:
        cmd_default = build_command(make_config("claude"), "hello")
        cmd_explicit = build_command(make_config("claude"), "hello", skip_permissions=True)
        assert cmd_default == cmd_explicit
        assert "--dangerously-skip-permissions" in cmd_default

    def test_codex_skip_permissions_false_with_session(self) -> None:
        cmd = build_command(make_config("codex"), "hello", session_id="t-1", skip_permissions=False)
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
        assert "resume" in cmd
        assert "t-1" in cmd

    def test_cursor_skip_permissions_false_with_session(self) -> None:
        cmd = build_command(make_config("cursor"), "hello", session_id="c-1", skip_permissions=False)
        assert "--force" not in cmd
        assert "--resume" in cmd
        assert "c-1" in cmd


class TestParseClaudeResponse:
    def test_json_output(self) -> None:
        stdout = '{"result": "hello world", "session_id": "sess-123"}'
        text, session_id, raw = parse_claude_response(stdout, "", 0)
        assert text == "hello world"
        assert session_id == "sess-123"
        assert raw == stdout

    def test_non_json_fallback(self) -> None:
        text, session_id, _raw = parse_claude_response("plain text", "", 0)
        assert text == "plain text"
        assert session_id is None

    def test_non_dict_json(self) -> None:
        text, session_id, _ = parse_claude_response('"just a string"', "", 0)
        assert text == '"just a string"'
        assert session_id is None


class TestParseCodexResponse:
    def test_jsonl_output(self) -> None:
        stdout = (
            '{"type":"thread.started","thread_id":"abc-123"}\n'
            '{"type":"turn.started"}\n'
            '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}\n'
            '{"type":"turn.completed"}\n'
        )
        text, session_id, _raw = parse_codex_response(stdout, "", 0)
        assert text == "OK"
        assert session_id == "abc-123"

    def test_non_jsonl_returns_empty(self) -> None:
        text, session_id, _ = parse_codex_response("plain text", "", 0)
        assert text == ""
        assert session_id is None

    def test_multiple_messages(self) -> None:
        stdout = (
            '{"type":"thread.started","thread_id":"t1"}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"line1"}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"line2"}}\n'
        )
        text, session_id, _ = parse_codex_response(stdout, "", 0)
        assert text == "line1\nline2"
        assert session_id == "t1"


class TestParseCursorResponse:
    def test_json_output_result_key(self) -> None:
        stdout = '{"result":"OK","session_id":"abc123"}'
        text, session_id, _ = parse_cursor_response(stdout, "", 0)
        assert text == "OK"
        assert session_id == "abc123"

    def test_json_output_text_key(self) -> None:
        stdout = '{"text":"hello","conversation_id":"conv-1"}'
        text, session_id, _ = parse_cursor_response(stdout, "", 0)
        assert text == "hello"
        assert session_id == "conv-1"

    def test_non_json_fallback(self) -> None:
        text, session_id, _ = parse_cursor_response("plain", "", 0)
        assert text == "plain"
        assert session_id is None


class TestParseResponseDispatch:
    def test_dispatches_to_claude(self) -> None:
        config = make_config("claude")
        stdout = '{"result": "test", "session_id": "s1"}'
        text, session_id, _ = parse_response(config, stdout, "", 0)
        assert text == "test"
        assert session_id == "s1"

    def test_unknown_backend_returns_raw(self) -> None:
        config = AgentConfig(name="x", backend="unknown", cli="x", resume_flag="")
        text, session_id, _ = parse_response(config, "raw output", "", 0)
        assert text == "raw output"
        assert session_id is None
