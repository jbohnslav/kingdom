"""Tests for council members and their CLI command building."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from kingdom.council import ClaudeMember, CodexMember, CursorAgentMember
from kingdom.council.base import AgentResponse, CouncilMember


class TestClaudeMember:
    def test_build_command_without_session(self) -> None:
        member = ClaudeMember()
        cmd = member.build_command("hello world")
        assert cmd == ["claude", "--print", "--output-format", "json", "-p", "hello world"]

    def test_build_command_with_session(self) -> None:
        member = ClaudeMember()
        member.session_id = "abc123"
        cmd = member.build_command("hello")
        # --resume must come before -p
        assert cmd == ["claude", "--print", "--output-format", "json", "--resume", "abc123", "-p", "hello"]


class TestCodexMember:
    def test_build_command_without_session(self) -> None:
        member = CodexMember()
        cmd = member.build_command("hello world")
        assert cmd == ["codex", "exec", "--json", "hello world"]

    def test_build_command_with_session(self) -> None:
        """Codex uses 'exec resume <thread_id>' for continuation."""
        member = CodexMember()
        member.session_id = "thread-123"
        cmd = member.build_command("hello")
        assert cmd == ["codex", "exec", "resume", "thread-123", "--json", "hello"]

    def test_parse_response_jsonl_extracts_thread_id(self) -> None:
        """Codex --json outputs JSONL; extract thread_id and agent message."""
        member = CodexMember()
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
        member = CodexMember()
        text, session_id, _raw = member.parse_response("plain text", "", 0)
        assert text == ""
        assert session_id is None


class TestCursorAgentMember:
    def test_build_command_without_session(self) -> None:
        member = CursorAgentMember()
        cmd = member.build_command("hello world")
        assert cmd[0] == "cursor"
        assert "agent" in cmd
        assert "--print" in cmd  # required for non-interactive use
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "hello world" in cmd
        # prompt is positional, not with -p flag
        assert "-p" not in cmd

    def test_build_command_with_session(self) -> None:
        member = CursorAgentMember()
        member.session_id = "conv-456"
        cmd = member.build_command("hello")
        assert "--resume" in cmd
        assert "conv-456" in cmd

    def test_parse_response_cursor_json_format(self) -> None:
        """Cursor returns result in 'result' key, session in 'session_id'."""
        member = CursorAgentMember()
        stdout = '{"type":"result","subtype":"success","is_error":false,"result":"OK","session_id":"abc123"}'
        text, session_id, _raw = member.parse_response(stdout, "", 0)
        assert text == "OK"
        assert session_id == "abc123"


class TestCouncilMemberQuery:
    """Tests for the query method on council members."""

    def test_query_passes_stdin_devnull(self) -> None:
        """Subprocess must use stdin=DEVNULL to prevent CLI hangs."""
        member = ClaudeMember()

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
        member = ClaudeMember()

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
        member = ClaudeMember()
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
        member = ClaudeMember()

        with patch("kingdom.council.base.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=30)):
            response = member.query("test prompt", timeout=30)

            assert response.error == "Timeout after 30s"
            assert response.text == ""

    def test_query_handles_command_not_found(self) -> None:
        """Query should handle missing CLI gracefully."""
        member = ClaudeMember()

        with patch("kingdom.council.base.subprocess.run", side_effect=FileNotFoundError()):
            response = member.query("test prompt", timeout=30)

            assert "Command not found" in response.error
            assert response.text == ""

    def test_query_captures_stderr_on_error(self) -> None:
        """Query should capture stderr when command fails."""
        member = ClaudeMember()

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Error: API key not set"
        mock_result.returncode = 1

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result):
            response = member.query("test prompt", timeout=30)

            assert response.error == "Error: API key not set"


class TestCouncilMemberQueryAllMembers:
    """Test that all member types pass stdin=DEVNULL."""

    @pytest.mark.parametrize("member_class,expected_name", [
        (ClaudeMember, "claude"),
        (CodexMember, "codex"),
        (CursorAgentMember, "agent"),
    ])
    def test_all_members_use_stdin_devnull(self, member_class, expected_name) -> None:
        """All council member types must use stdin=DEVNULL."""
        member = member_class()
        assert member.name == expected_name

        mock_result = MagicMock()
        mock_result.stdout = '{"result": "ok"}'
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("kingdom.council.base.subprocess.run", return_value=mock_result) as mock_run:
            member.query("test", timeout=10)

            assert mock_run.call_args.kwargs.get("stdin") == subprocess.DEVNULL
