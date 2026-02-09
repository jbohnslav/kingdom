"""Tests for agent configuration model."""

from pathlib import Path

import pytest

from kingdom.agent import (
    DEFAULT_AGENTS,
    AgentConfig,
    agents_root,
    build_command,
    create_default_agent_files,
    list_agents,
    load_agent,
    parse_agent_file,
    parse_claude_response,
    parse_codex_response,
    parse_cursor_response,
    parse_response,
    serialize_agent_file,
)


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

    def test_optional_fields(self) -> None:
        config = AgentConfig(
            name="test",
            backend="claude_code",
            cli="test --flag",
            resume_flag="--resume",
            version_command="test --version",
            install_hint="Install test",
        )
        assert config.version_command == "test --version"
        assert config.install_hint == "Install test"


class TestParseAgentFile:
    def test_parse_minimal(self) -> None:
        content = "---\nname: myagent\nbackend: claude_code\ncli: claude --print\nresume_flag: --resume\n---\n"
        config = parse_agent_file(content)
        assert config.name == "myagent"
        assert config.backend == "claude_code"
        assert config.cli == "claude --print"
        assert config.resume_flag == "--resume"

    def test_parse_all_fields(self) -> None:
        content = (
            "---\n"
            "name: claude\n"
            "backend: claude_code\n"
            "cli: claude --print --output-format json\n"
            "resume_flag: --resume\n"
            "version_command: claude --version\n"
            "install_hint: Install Claude Code: https://docs.anthropic.com\n"
            "---\n"
        )
        config = parse_agent_file(content)
        assert config.name == "claude"
        assert config.backend == "claude_code"
        assert config.cli == "claude --print --output-format json"
        assert config.resume_flag == "--resume"
        assert config.version_command == "claude --version"
        assert config.install_hint == "Install Claude Code: https://docs.anthropic.com"

    def test_parse_missing_frontmatter(self) -> None:
        with pytest.raises(ValueError, match="must start with YAML frontmatter"):
            parse_agent_file("no frontmatter here")

    def test_parse_missing_closing(self) -> None:
        with pytest.raises(ValueError, match="missing closing"):
            parse_agent_file("---\nname: test\n")

    def test_parse_missing_required_fields(self) -> None:
        with pytest.raises(ValueError, match="must have name, backend, and cli"):
            parse_agent_file("---\nname: test\n---\n")

    def test_parse_empty_resume_flag(self) -> None:
        content = "---\nname: test\nbackend: test\ncli: test --flag\n---\n"
        config = parse_agent_file(content)
        assert config.resume_flag == ""

    def test_parse_with_body_content(self) -> None:
        """Body content after frontmatter is ignored."""
        content = "---\nname: test\nbackend: test\ncli: test\nresume_flag: --r\n---\nSome body text here.\n"
        config = parse_agent_file(content)
        assert config.name == "test"


class TestSerializeAgentFile:
    def test_roundtrip(self) -> None:
        config = AgentConfig(
            name="claude",
            backend="claude_code",
            cli="claude --print --output-format json",
            resume_flag="--resume",
            version_command="claude --version",
            install_hint="Install Claude Code",
        )
        serialized = serialize_agent_file(config)
        parsed = parse_agent_file(serialized)
        assert parsed.name == config.name
        assert parsed.backend == config.backend
        assert parsed.cli == config.cli
        assert parsed.resume_flag == config.resume_flag
        assert parsed.version_command == config.version_command
        assert parsed.install_hint == config.install_hint

    def test_omits_empty_optional_fields(self) -> None:
        config = AgentConfig(name="test", backend="test", cli="test", resume_flag="--r")
        serialized = serialize_agent_file(config)
        assert "version_command" not in serialized
        assert "install_hint" not in serialized


class TestLoadAgent:
    def test_load_existing(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".kd" / "agents"
        agents_dir.mkdir(parents=True)
        content = "---\nname: claude\nbackend: claude_code\ncli: claude --print\nresume_flag: --resume\n---\n"
        (agents_dir / "claude.md").write_text(content)

        config = load_agent("claude", tmp_path)
        assert config.name == "claude"
        assert config.backend == "claude_code"

    def test_load_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_agent("nonexistent", tmp_path)


class TestListAgents:
    def test_list_empty(self, tmp_path: Path) -> None:
        assert list_agents(tmp_path) == []

    def test_list_agents(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".kd" / "agents"
        agents_dir.mkdir(parents=True)

        for name in ["alpha", "beta"]:
            content = f"---\nname: {name}\nbackend: test\ncli: {name} --run\nresume_flag: --r\n---\n"
            (agents_dir / f"{name}.md").write_text(content)

        agents = list_agents(tmp_path)
        assert len(agents) == 2
        assert agents[0].name == "alpha"
        assert agents[1].name == "beta"

    def test_list_skips_invalid_files(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".kd" / "agents"
        agents_dir.mkdir(parents=True)

        # Valid file
        (agents_dir / "good.md").write_text("---\nname: good\nbackend: test\ncli: good\n---\n")
        # Invalid file (no frontmatter)
        (agents_dir / "bad.md").write_text("not a valid agent file")

        agents = list_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0].name == "good"


class TestDefaultAgents:
    def test_default_agents_defined(self) -> None:
        assert "claude" in DEFAULT_AGENTS
        assert "codex" in DEFAULT_AGENTS
        assert "cursor" in DEFAULT_AGENTS

    def test_claude_defaults(self) -> None:
        c = DEFAULT_AGENTS["claude"]
        assert c.backend == "claude_code"
        assert "claude" in c.cli
        assert c.resume_flag == "--resume"

    def test_codex_defaults(self) -> None:
        c = DEFAULT_AGENTS["codex"]
        assert c.backend == "codex"
        assert "codex" in c.cli
        assert c.resume_flag == "resume"

    def test_cursor_defaults(self) -> None:
        c = DEFAULT_AGENTS["cursor"]
        assert c.backend == "cursor"
        assert "agent" in c.cli
        assert c.resume_flag == "--resume"


class TestCreateDefaultAgentFiles:
    def test_creates_files(self, tmp_path: Path) -> None:
        (tmp_path / ".kd").mkdir()
        paths = create_default_agent_files(tmp_path)
        assert len(paths) == 3
        for path in paths:
            assert path.exists()
            assert path.suffix == ".md"

    def test_idempotent(self, tmp_path: Path) -> None:
        (tmp_path / ".kd").mkdir()
        create_default_agent_files(tmp_path)
        # Modify a file
        claude_path = tmp_path / ".kd" / "agents" / "claude.md"
        original = claude_path.read_text()
        claude_path.write_text("---\nname: claude\nbackend: claude_code\ncli: custom\nresume_flag: --r\n---\n")

        # Should not overwrite
        create_default_agent_files(tmp_path)
        assert claude_path.read_text() != original  # custom content preserved

    def test_created_files_are_loadable(self, tmp_path: Path) -> None:
        (tmp_path / ".kd").mkdir()
        create_default_agent_files(tmp_path)
        agents = list_agents(tmp_path)
        assert len(agents) == 3
        names = {a.name for a in agents}
        assert names == {"claude", "codex", "cursor"}


class TestBuildCommand:
    def test_claude_without_session(self) -> None:
        cmd = build_command(DEFAULT_AGENTS["claude"], "hello world")
        assert cmd == [
            "claude", "--dangerously-skip-permissions", "--print", "--output-format", "json", "-p", "hello world",
        ]

    def test_claude_with_session(self) -> None:
        cmd = build_command(DEFAULT_AGENTS["claude"], "hello", session_id="abc123")
        assert cmd == [
            "claude", "--dangerously-skip-permissions", "--print", "--output-format", "json",
            "--resume", "abc123", "-p", "hello",
        ]

    def test_codex_without_session(self) -> None:
        cmd = build_command(DEFAULT_AGENTS["codex"], "hello world")
        assert cmd == [
            "codex", "--dangerously-bypass-approvals-and-sandbox", "exec", "--json", "hello world",
        ]

    def test_codex_with_session(self) -> None:
        cmd = build_command(DEFAULT_AGENTS["codex"], "hello", session_id="thread-123")
        assert cmd == [
            "codex", "--dangerously-bypass-approvals-and-sandbox", "exec", "resume", "thread-123", "--json", "hello",
        ]

    def test_cursor_without_session(self) -> None:
        cmd = build_command(DEFAULT_AGENTS["cursor"], "hello world")
        assert cmd == [
            "agent", "--force", "--sandbox", "disabled", "--print", "--output-format", "json", "hello world",
        ]

    def test_cursor_with_session(self) -> None:
        cmd = build_command(DEFAULT_AGENTS["cursor"], "hello", session_id="conv-456")
        assert cmd == [
            "agent", "--force", "--sandbox", "disabled", "--print", "--output-format", "json",
            "hello", "--resume", "conv-456",
        ]

    def test_unknown_backend_raises(self) -> None:
        config = AgentConfig(name="bad", backend="unknown", cli="bad", resume_flag="")
        with pytest.raises(ValueError, match="Unknown backend"):
            build_command(config, "test")

    def test_codex_missing_exec_raises(self) -> None:
        config = AgentConfig(name="codex", backend="codex", cli="codex --json", resume_flag="resume")
        with pytest.raises(ValueError, match="must contain 'exec'"):
            build_command(config, "hello", session_id="thread-1")


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
        config = DEFAULT_AGENTS["claude"]
        stdout = '{"result": "test", "session_id": "s1"}'
        text, session_id, _ = parse_response(config, stdout, "", 0)
        assert text == "test"
        assert session_id == "s1"

    def test_unknown_backend_returns_raw(self) -> None:
        config = AgentConfig(name="x", backend="unknown", cli="x", resume_flag="")
        text, session_id, _ = parse_response(config, "raw output", "", 0)
        assert text == "raw output"
        assert session_id is None


class TestAgentsRoot:
    def test_path(self, tmp_path: Path) -> None:
        assert agents_root(tmp_path) == tmp_path / ".kd" / "agents"
