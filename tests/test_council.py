"""Tests for council members and their CLI command building."""

from kingdom.council import ClaudeMember, CodexMember, CursorAgentMember


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
