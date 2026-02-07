"""Tests for council members and their CLI command building."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kingdom.agent import DEFAULT_AGENTS, AgentConfig
from kingdom.council.base import AgentResponse, CouncilMember
from kingdom.council.council import Council


def make_member(name: str) -> CouncilMember:
    """Create a CouncilMember from default agent config."""
    return CouncilMember(config=DEFAULT_AGENTS[name])


class TestClaudeMember:
    def test_build_command_without_session(self) -> None:
        member = make_member("claude")
        cmd = member.build_command("hello world")
        assert cmd == ["claude", "--print", "--output-format", "json", "-p", "hello world"]

    def test_build_command_with_session(self) -> None:
        member = make_member("claude")
        member.session_id = "abc123"
        cmd = member.build_command("hello")
        # --resume must come before -p
        assert cmd == ["claude", "--print", "--output-format", "json", "--resume", "abc123", "-p", "hello"]


class TestCodexMember:
    def test_build_command_without_session(self) -> None:
        member = make_member("codex")
        cmd = member.build_command("hello world")
        assert cmd == ["codex", "exec", "--json", "hello world"]

    def test_build_command_with_session(self) -> None:
        """Codex uses 'exec resume <thread_id>' for continuation."""
        member = make_member("codex")
        member.session_id = "thread-123"
        cmd = member.build_command("hello")
        assert cmd == ["codex", "exec", "resume", "thread-123", "--json", "hello"]

    def test_parse_response_jsonl_extracts_thread_id(self) -> None:
        """Codex --json outputs JSONL; extract thread_id and agent message."""
        member = make_member("codex")
        stdout = (
            '{"type":"thread.started","thread_id":"abc-123"}\n'
            '{"type":"turn.started"}\n'
            '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}\n'
            '{"type":"turn.completed"}\n'
        )
        text, session_id, _raw = member.parse_response(stdout, "", 0)
        assert text == "OK"
        assert session_id == "abc-123"

    def test_parse_response_non_jsonl_returns_empty(self) -> None:
        """Non-JSONL input returns empty text (graceful handling)."""
        member = make_member("codex")
        text, session_id, _raw = member.parse_response("plain text", "", 0)
        assert text == ""
        assert session_id is None


class TestCursorAgentMember:
    def test_build_command_without_session(self) -> None:
        member = make_member("cursor")
        cmd = member.build_command("hello world")
        assert cmd[0] == "agent"
        assert "--print" in cmd  # required for non-interactive use
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "hello world" in cmd
        # prompt is positional, not with -p flag
        assert "-p" not in cmd

    def test_build_command_with_session(self) -> None:
        member = make_member("cursor")
        member.session_id = "conv-456"
        cmd = member.build_command("hello")
        assert "--resume" in cmd
        assert "conv-456" in cmd

    def test_parse_response_cursor_json_format(self) -> None:
        """Cursor returns result in 'result' key, session in 'session_id'."""
        member = make_member("cursor")
        stdout = '{"type":"result","subtype":"success","is_error":false,"result":"OK","session_id":"abc123"}'
        text, session_id, _raw = member.parse_response(stdout, "", 0)
        assert text == "OK"
        assert session_id == "abc123"


class TestCouncilMemberQuery:
    """Tests for the query method on council members."""

    def test_query_passes_stdin_devnull(self) -> None:
        """Subprocess must use stdin=DEVNULL to prevent CLI hangs."""
        member = make_member("claude")

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "hello", "session_id": "sess-123"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result) as mock_run:
            member.query("test prompt", timeout=30)

            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs.get("stdin") == subprocess.DEVNULL, "stdin must be DEVNULL to prevent hangs"

    def test_query_returns_agent_response(self) -> None:
        """Query should return an AgentResponse with text and timing."""
        member = make_member("claude")

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "test response", "session_id": "sess-456"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
            response = member.query("test prompt", timeout=30)

            assert isinstance(response, AgentResponse)
            assert response.name == "claude"
            assert response.text == "test response"
            assert response.error is None
            assert response.elapsed > 0

    def test_query_updates_session_id(self) -> None:
        """Query should update member's session_id from response."""
        member = make_member("claude")
        assert member.session_id is None

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "hello", "session_id": "new-session-789"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
            member.query("test prompt", timeout=30)

            assert member.session_id == "new-session-789"

    def test_query_handles_timeout(self) -> None:
        """Query should handle subprocess timeout gracefully."""
        member = make_member("claude")

        with patch(
            "kingdom.council.base.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=30)
        ):
            response = member.query("test prompt", timeout=30)

            assert response.error == "Timeout after 30s"
            assert response.text == ""

    def test_query_handles_command_not_found(self) -> None:
        """Query should handle missing CLI gracefully."""
        member = make_member("claude")

        with patch("kingdom.council.base.subprocess.run", side_effect=FileNotFoundError()):
            response = member.query("test prompt", timeout=30)

            assert "Command not found" in response.error
            assert response.text == ""

    def test_query_captures_stderr_on_error(self) -> None:
        """Query should capture stderr when command fails."""
        member = make_member("claude")

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error: API key not set"
        mock_result.returncode = 1

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
            response = member.query("test prompt", timeout=30)

            assert response.error == "Error: API key not set"


class TestCouncilMemberQueryAllMembers:
    """Test that all member types pass stdin=DEVNULL."""

    @pytest.mark.parametrize(
        "agent_name,expected_name",
        [
            ("claude", "claude"),
            ("codex", "codex"),
            ("cursor", "cursor"),
        ],
    )
    def test_all_members_use_stdin_devnull(self, agent_name, expected_name) -> None:
        """All council member types must use stdin=DEVNULL."""
        member = make_member(agent_name)
        assert member.name == expected_name

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "ok"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result) as mock_run:
            member.query("test", timeout=10)

            assert mock_run.call_args.kwargs.get("stdin") == subprocess.DEVNULL


class TestCouncilMemberQueryConfigErrors:
    """Test that config errors return structured AgentResponse instead of crashing."""

    def test_query_handles_unknown_backend(self) -> None:
        """Unknown backend should return AgentResponse with error, not raise."""
        config = AgentConfig(name="bad", backend="unknown", cli="bad", resume_flag="")
        member = CouncilMember(config=config)

        response = member.query("test prompt", timeout=30)

        assert response.error is not None
        assert "Invalid agent config" in response.error
        assert response.text == ""

    def test_query_handles_codex_missing_exec(self) -> None:
        """Codex config without 'exec' should return error, not raise."""
        config = AgentConfig(name="codex", backend="codex", cli="codex --json", resume_flag="resume")
        member = CouncilMember(config=config, session_id="thread-1")

        response = member.query("test prompt", timeout=30)

        assert response.error is not None
        assert "Invalid agent config" in response.error


class TestCouncilCreateValidation:
    """Test that Council.create() validates agent configs."""

    def test_create_uses_defaults_when_no_agents_dir(self, tmp_path: Path) -> None:
        """No .kd/agents/ dir should use defaults without error."""
        council = Council.create(base=tmp_path)
        assert len(council.members) == 3
        names = {m.name for m in council.members}
        assert names == {"claude", "codex", "cursor"}

    def test_create_uses_agent_files(self, tmp_path: Path) -> None:
        """Valid agent files should be loaded."""
        agents_dir = tmp_path / ".kd" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "myagent.md").write_text(
            "---\nname: myagent\nbackend: claude_code\ncli: claude --print\nresume_flag: --resume\n---\n"
        )

        council = Council.create(base=tmp_path)
        assert len(council.members) == 1
        assert council.members[0].name == "myagent"

    def test_create_raises_when_all_agent_files_broken(self, tmp_path: Path) -> None:
        """If agent files exist but all fail to parse, raise ValueError."""
        agents_dir = tmp_path / ".kd" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "broken.md").write_text("not valid frontmatter")

        with pytest.raises(ValueError, match="none could be parsed"):
            Council.create(base=tmp_path)

    def test_create_uses_defaults_when_agents_dir_empty(self, tmp_path: Path) -> None:
        """Empty .kd/agents/ dir should use defaults without error."""
        agents_dir = tmp_path / ".kd" / "agents"
        agents_dir.mkdir(parents=True)

        council = Council.create(base=tmp_path)
        assert len(council.members) == 3
