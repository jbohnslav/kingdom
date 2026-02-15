"""Tests for council members and their CLI command building."""

import importlib.util
import io
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kingdom.agent import AgentConfig, resolve_agent
from kingdom.config import DEFAULT_AGENTS
from kingdom.council.base import AgentResponse, CouncilMember
from kingdom.council.council import Council
from kingdom.session import AgentState, get_agent_state, session_path, set_agent_state
from kingdom.state import ensure_branch_layout

PREAMBLE = CouncilMember.COUNCIL_PREAMBLE


def make_member(name: str) -> CouncilMember:
    """Create a CouncilMember from default agent config."""
    return CouncilMember(config=resolve_agent(name, DEFAULT_AGENTS[name]))


def mock_popen(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock Popen that yields stdout/stderr line-by-line."""
    proc = MagicMock()
    proc.stdout = io.StringIO(stdout)
    proc.stderr = io.StringIO(stderr)
    proc.returncode = returncode
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    return proc


class TestCouncilMemberPermissions:
    """Council members should NOT include skip-permissions flags."""

    def test_claude_no_skip_permissions(self) -> None:
        member = make_member("claude")
        cmd = member.build_command("hello world")
        assert "--dangerously-skip-permissions" not in cmd
        assert "--allowedTools" in cmd
        assert "Read" in cmd
        assert "Edit" not in cmd
        assert "Write" not in cmd
        assert "Bash" in cmd

    def test_codex_no_skip_permissions(self) -> None:
        member = make_member("codex")
        cmd = member.build_command("hello world")
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
        assert "disk-full-read-access" in " ".join(cmd)

    def test_cursor_no_skip_permissions(self) -> None:
        member = make_member("cursor")
        cmd = member.build_command("hello world")
        assert "--force" not in cmd
        assert "--sandbox" not in cmd
        assert "--mode" in cmd
        assert "ask" in cmd


class TestClaudeMember:
    def test_build_command_without_session(self) -> None:
        member = make_member("claude")
        cmd = member.build_command("hello world")
        assert cmd[0] == "claude"
        assert "--allowedTools" in cmd
        assert "-p" in cmd
        assert PREAMBLE + "hello world" in cmd
        assert "--dangerously-skip-permissions" not in cmd
        # Council uses streaming=True
        fmt_idx = cmd.index("--output-format")
        assert cmd[fmt_idx + 1] == "stream-json"
        assert "--verbose" in cmd
        assert "--include-partial-messages" in cmd

    def test_build_command_with_session(self) -> None:
        member = make_member("claude")
        member.session_id = "abc123"
        cmd = member.build_command("hello")
        assert "--resume" in cmd
        assert "abc123" in cmd
        assert "--allowedTools" in cmd
        assert PREAMBLE + "hello" in cmd
        fmt_idx = cmd.index("--output-format")
        assert cmd[fmt_idx + 1] == "stream-json"


class TestCodexMember:
    def test_build_command_without_session(self) -> None:
        member = make_member("codex")
        cmd = member.build_command("hello world")
        assert cmd[0] == "codex"
        assert "disk-full-read-access" in " ".join(cmd)
        assert PREAMBLE + "hello world" in cmd
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd

    def test_build_command_with_session(self) -> None:
        """Codex uses 'exec resume <thread_id>' for continuation."""
        member = make_member("codex")
        member.session_id = "thread-123"
        cmd = member.build_command("hello")
        assert "resume" in cmd
        assert "thread-123" in cmd
        assert PREAMBLE + "hello" in cmd

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
        fmt_idx = cmd.index("--output-format")
        assert cmd[fmt_idx + 1] == "stream-json"
        assert PREAMBLE + "hello world" in cmd
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
        proc = mock_popen(stdout='{"result": "hello", "session_id": "sess-123"}\n')

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc) as mock_cls:
            member.query("test prompt", timeout=30)

            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs.get("stdin") == subprocess.DEVNULL, "stdin must be DEVNULL to prevent hangs"

    def test_query_passes_council_identity_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Council subprocesses should get explicit role/name identity env vars."""
        monkeypatch.setenv("CLAUDECODE", "1")
        member = make_member("claude")
        proc = mock_popen(stdout='{"result": "hello", "session_id": "sess-123"}\n')

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc) as mock_cls:
            member.query("test prompt", timeout=30)

            call_kwargs = mock_cls.call_args.kwargs
            env = call_kwargs.get("env", {})
            assert env.get("KD_ROLE") == "council"
            assert env.get("KD_AGENT_NAME") == "claude"
            assert "CLAUDECODE" not in env

    def test_query_returns_agent_response(self) -> None:
        """Query should return an AgentResponse with text and timing."""
        member = make_member("claude")
        proc = mock_popen(stdout='{"result": "test response", "session_id": "sess-456"}\n')

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc):
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
        proc = mock_popen(stdout='{"result": "hello", "session_id": "new-session-789"}\n')

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc):
            member.query("test prompt", timeout=30)

            assert member.session_id == "new-session-789"

    def test_query_handles_timeout_with_partial_output(self, tmp_path: Path) -> None:
        """Timeout should capture partial output and stream it to file."""
        member = make_member("claude")
        partial_output = "partial line 1\npartial line 2\n"

        proc = MagicMock()
        proc.stdout = io.StringIO(partial_output)
        proc.stderr = io.StringIO("")
        proc.returncode = -9
        # poll() returns None (still running) so the timeout loop fires
        proc.poll.return_value = None
        proc.kill.return_value = None
        proc.wait.return_value = -9

        stream_path = tmp_path / "stream.md"

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc):
            response = member.query("test prompt", timeout=0, stream_path=stream_path)

        assert response.error is not None
        assert "Timeout" in response.error
        assert response.text == partial_output
        proc.kill.assert_called_once()
        assert stream_path.read_text() == partial_output

    def test_query_handles_command_not_found(self) -> None:
        """Query should handle missing CLI gracefully."""
        member = make_member("claude")

        with patch("kingdom.council.base.subprocess.Popen", side_effect=FileNotFoundError()):
            response = member.query("test prompt", timeout=30)

            assert "Command not found" in response.error
            assert response.text == ""

    def test_query_captures_stderr_on_error(self) -> None:
        """Query should capture stderr when command fails."""
        member = make_member("claude")
        proc = mock_popen(stdout="", stderr="Error: API key not set\n", returncode=1)

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc):
            response = member.query("test prompt", timeout=30)

            assert response.error == "Error: API key not set"

    def test_query_streams_to_file(self, tmp_path: Path) -> None:
        """Query should tee stdout to stream_path when provided."""
        member = make_member("claude")
        proc = mock_popen(stdout='{"result": "streamed", "session_id": "s1"}\n')
        stream_path = tmp_path / "stream.md"

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc):
            response = member.query("test prompt", timeout=30, stream_path=stream_path)

        assert response.text == "streamed"
        assert stream_path.read_text() == '{"result": "streamed", "session_id": "s1"}\n'


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
        proc = mock_popen(stdout='{"result": "ok"}\n')

        with patch("kingdom.council.base.subprocess.Popen", return_value=proc) as mock_cls:
            member.query("test", timeout=10)

            assert mock_cls.call_args.kwargs.get("stdin") == subprocess.DEVNULL


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
    """Test that Council.create() builds from config."""

    def test_create_uses_defaults_when_no_config(self, tmp_path: Path) -> None:
        """No .kd/config.json should use defaults without error."""
        (tmp_path / ".kd").mkdir(parents=True, exist_ok=True)
        council = Council.create(base=tmp_path)
        assert len(council.members) == 3
        names = {m.name for m in council.members}
        assert names == {"claude", "codex", "cursor"}

    def test_create_respects_council_members_config(self, tmp_path: Path) -> None:
        """Council should only include agents listed in config.council.members."""
        import json

        kd = tmp_path / ".kd"
        kd.mkdir(parents=True)
        (kd / "config.json").write_text(json.dumps({"council": {"members": ["claude", "codex"]}}))

        council = Council.create(base=tmp_path)
        assert len(council.members) == 2
        names = {m.name for m in council.members}
        assert names == {"claude", "codex"}

    def test_create_uses_config_timeout(self, tmp_path: Path) -> None:
        """Council timeout should come from config."""
        import json

        kd = tmp_path / ".kd"
        kd.mkdir(parents=True)
        (kd / "config.json").write_text(json.dumps({"council": {"timeout": 120}}))

        council = Council.create(base=tmp_path)
        assert council.timeout == 120

    def test_create_passes_global_phase_prompt(self, tmp_path: Path) -> None:
        """Global council prompt should be set on members."""
        import json

        kd = tmp_path / ".kd"
        kd.mkdir(parents=True)
        data = {
            "prompts": {"council": "Analyze only, no implementation."},
            "council": {"members": ["claude"]},
        }
        (kd / "config.json").write_text(json.dumps(data))

        council = Council.create(base=tmp_path)
        assert council.members[0].phase_prompt == "Analyze only, no implementation."

    def test_create_agent_phase_prompt_overrides_global(self, tmp_path: Path) -> None:
        """Agent-specific council prompt overrides global."""
        import json

        kd = tmp_path / ".kd"
        kd.mkdir(parents=True)
        data = {
            "agents": {
                "claude": {
                    "backend": "claude_code",
                    "prompts": {"council": "Focus on architecture."},
                }
            },
            "prompts": {"council": "Global prompt."},
            "council": {"members": ["claude"]},
        }
        (kd / "config.json").write_text(json.dumps(data))

        council = Council.create(base=tmp_path)
        assert council.members[0].phase_prompt == "Focus on architecture."

    def test_create_passes_agent_prompt(self, tmp_path: Path) -> None:
        """Agent prompt (always additive) should be set on members."""
        import json

        kd = tmp_path / ".kd"
        kd.mkdir(parents=True)
        data = {
            "agents": {"claude": {"backend": "claude_code", "prompt": "Be concise."}},
            "council": {"members": ["claude"]},
        }
        (kd / "config.json").write_text(json.dumps(data))

        council = Council.create(base=tmp_path)
        assert council.members[0].agent_prompt == "Be concise."


class TestPromptMerging:
    """Test prompt merge order in CouncilMember.build_command()."""

    def test_preamble_only(self) -> None:
        """With no config prompts, just preamble + user prompt."""
        member = make_member("claude")
        cmd = member.build_command("What do you think?")
        prompt = cmd[cmd.index("-p") + 1]
        assert prompt.startswith(CouncilMember.COUNCIL_PREAMBLE)
        assert prompt.endswith("What do you think?")

    def test_phase_prompt_inserted(self) -> None:
        """Phase prompt appears between preamble and user prompt."""
        member = make_member("claude")
        member.phase_prompt = "Analyze only."
        cmd = member.build_command("What do you think?")
        prompt = cmd[cmd.index("-p") + 1]
        assert "Analyze only." in prompt
        assert prompt.index(CouncilMember.COUNCIL_PREAMBLE) < prompt.index("Analyze only.")
        assert prompt.index("Analyze only.") < prompt.index("What do you think?")

    def test_agent_prompt_inserted(self) -> None:
        """Agent prompt appears between preamble and user prompt."""
        member = make_member("claude")
        member.agent_prompt = "Be concise."
        cmd = member.build_command("What do you think?")
        prompt = cmd[cmd.index("-p") + 1]
        assert "Be concise." in prompt
        assert prompt.index("Be concise.") < prompt.index("What do you think?")

    def test_full_merge_order(self) -> None:
        """Preamble + phase + agent + user in correct order."""
        member = make_member("claude")
        member.phase_prompt = "Phase instruction."
        member.agent_prompt = "Agent personality."
        cmd = member.build_command("User question?")
        prompt = cmd[cmd.index("-p") + 1]
        preamble_end = prompt.index(CouncilMember.COUNCIL_PREAMBLE) + len(CouncilMember.COUNCIL_PREAMBLE)
        phase_idx = prompt.index("Phase instruction.")
        agent_idx = prompt.index("Agent personality.")
        user_idx = prompt.index("User question?")
        assert preamble_end <= phase_idx < agent_idx < user_idx

    def test_no_prompts_is_same_as_before(self) -> None:
        """Empty prompts should produce same result as old behavior."""
        member = make_member("claude")
        cmd = member.build_command("hello")
        prompt = cmd[cmd.index("-p") + 1]
        assert prompt == CouncilMember.COUNCIL_PREAMBLE + "hello"


BRANCH = "feature/test-council"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    return tmp_path


class TestCouncilSessions:
    """Tests for council load/save sessions using agent state."""

    def test_load_sessions_reads_agent_state(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude", resume_id="sess-abc"))
        set_agent_state(project, BRANCH, "codex", AgentState(name="codex", resume_id="thread-123"))

        council = Council.create(base=project)
        council.load_sessions(project, BRANCH)

        claude = council.get_member("claude")
        codex = council.get_member("codex")
        assert claude.session_id == "sess-abc"
        assert codex.session_id == "thread-123"

    def test_load_sessions_no_state_leaves_none(self, project: Path) -> None:
        council = Council.create(base=project)
        council.load_sessions(project, BRANCH)

        for member in council.members:
            assert member.session_id is None

    def test_save_sessions_writes_agent_state(self, project: Path) -> None:
        council = Council.create(base=project)
        council.get_member("claude").session_id = "sess-new"
        council.get_member("codex").session_id = "thread-new"

        council.save_sessions(project, BRANCH)

        claude_state = get_agent_state(project, BRANCH, "claude")
        codex_state = get_agent_state(project, BRANCH, "codex")
        assert claude_state.resume_id == "sess-new"
        assert codex_state.resume_id == "thread-new"

    def test_save_sessions_clears_resume_id(self, project: Path) -> None:
        set_agent_state(project, BRANCH, "claude", AgentState(name="claude", resume_id="old-sess"))

        council = Council.create(base=project)
        council.load_sessions(project, BRANCH)
        council.reset_sessions()
        council.save_sessions(project, BRANCH)

        state = get_agent_state(project, BRANCH, "claude")
        assert state.resume_id is None

    def test_save_preserves_other_agent_state_fields(self, project: Path) -> None:
        set_agent_state(
            project,
            BRANCH,
            "claude",
            AgentState(
                name="claude",
                status="working",
                resume_id="old",
                ticket="kin-042",
            ),
        )

        council = Council.create(base=project)
        council.load_sessions(project, BRANCH)
        council.get_member("claude").session_id = "new-sess"
        council.save_sessions(project, BRANCH)

        state = get_agent_state(project, BRANCH, "claude")
        assert state.resume_id == "new-sess"
        assert state.status == "working"
        assert state.ticket == "kin-042"

    def test_roundtrip_load_save_load(self, project: Path) -> None:
        council = Council.create(base=project)
        council.get_member("claude").session_id = "sess-rt"
        council.save_sessions(project, BRANCH)

        council2 = Council.create(base=project)
        council2.load_sessions(project, BRANCH)
        assert council2.get_member("claude").session_id == "sess-rt"

    def test_legacy_session_files_migrated_on_load(self, project: Path) -> None:
        """Legacy .session files should be migrated via get_agent_state."""
        from kingdom.session import legacy_session_path

        old_path = legacy_session_path(project, BRANCH, "claude")
        old_path.write_text("legacy-sess-id\n", encoding="utf-8")

        council = Council.create(base=project)
        council.load_sessions(project, BRANCH)

        assert council.get_member("claude").session_id == "legacy-sess-id"
        assert not old_path.exists()
        assert session_path(project, BRANCH, "claude").exists()


class TestQueryToThread:
    """Tests for Council.query_to_thread()."""

    def test_writes_responses_to_thread(self, project: Path) -> None:
        from kingdom.thread import create_thread, list_messages

        thread_id = "council-test"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex", "cursor"], "council")

        council = Council.create(base=project)

        with patch("kingdom.council.base.subprocess.Popen") as mock_cls:
            mock_cls.side_effect = lambda *a, **kw: mock_popen(stdout='{"result": "test response"}\n')
            responses = council.query_to_thread("test prompt", project, BRANCH, thread_id)

        assert len(responses) == 3
        messages = list_messages(project, BRANCH, thread_id)
        # 3 response messages (one per member)
        assert len(messages) == 3
        senders = {m.from_ for m in messages}
        assert senders == {"claude", "codex", "cursor"}

    def test_calls_callback_for_each_response(self, project: Path) -> None:
        from kingdom.thread import create_thread

        thread_id = "council-cb"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex", "cursor"], "council")

        council = Council.create(base=project)

        callback_calls = []

        def on_response(name, response):
            callback_calls.append(name)

        with patch("kingdom.council.base.subprocess.Popen") as mock_cls:
            mock_cls.side_effect = lambda *a, **kw: mock_popen(stdout='{"result": "ok"}\n')
            council.query_to_thread("test", project, BRANCH, thread_id, callback=on_response)

        assert len(callback_calls) == 3
        assert set(callback_calls) == {"claude", "codex", "cursor"}

    def test_handles_errors_in_thread(self, project: Path) -> None:
        from kingdom.thread import create_thread, list_messages

        thread_id = "council-err"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex", "cursor"], "council")

        council = Council.create(base=project)

        with patch("kingdom.council.base.subprocess.Popen", side_effect=FileNotFoundError()):
            responses = council.query_to_thread("test", project, BRANCH, thread_id)

        # All should have errors
        for resp in responses.values():
            assert resp.error is not None

        # All should still be written to thread
        messages = list_messages(project, BRANCH, thread_id)
        assert len(messages) == 3


_has_worker = importlib.util.find_spec("kingdom.council.worker") is not None


@pytest.mark.skipif(not _has_worker, reason="kingdom.council.worker not available")
class TestCouncilWorker:
    """Tests for the council async worker module."""

    def test_worker_queries_all_members(self, project: Path) -> None:
        from kingdom.council.worker import main
        from kingdom.thread import create_thread, list_messages

        thread_id = "council-work"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex", "cursor"], "council")

        with patch("kingdom.council.base.subprocess.Popen") as mock_cls:
            mock_cls.side_effect = lambda *a, **kw: mock_popen(stdout='{"result": "worker response"}\n')
            main(
                [
                    "--base",
                    str(project),
                    "--feature",
                    BRANCH,
                    "--thread-id",
                    thread_id,
                    "--prompt",
                    "test prompt",
                    "--timeout",
                    "10",
                ]
            )

        messages = list_messages(project, BRANCH, thread_id)
        assert len(messages) == 3
        senders = {m.from_ for m in messages}
        assert senders == {"claude", "codex", "cursor"}

    def test_worker_queries_single_member(self, project: Path) -> None:
        from kingdom.council.worker import main
        from kingdom.thread import create_thread, list_messages

        thread_id = "council-single"
        create_thread(project, BRANCH, thread_id, ["king", "codex"], "council")

        with patch("kingdom.council.base.subprocess.Popen") as mock_cls:
            mock_cls.return_value = mock_popen(stdout='{"result": "codex says hi"}\n')
            main(
                [
                    "--base",
                    str(project),
                    "--feature",
                    BRANCH,
                    "--thread-id",
                    thread_id,
                    "--prompt",
                    "targeted prompt",
                    "--timeout",
                    "10",
                    "--to",
                    "codex",
                ]
            )

        messages = list_messages(project, BRANCH, thread_id)
        assert len(messages) == 1
        assert messages[0].from_ == "codex"

    def test_worker_unknown_member_exits(self, project: Path) -> None:
        from kingdom.council.worker import main

        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--base",
                    str(project),
                    "--feature",
                    BRANCH,
                    "--thread-id",
                    "council-err",
                    "--prompt",
                    "test",
                    "--to",
                    "nonexistent",
                ]
            )

        assert exc_info.value.code == 1

    def test_worker_saves_sessions(self, project: Path) -> None:
        from kingdom.council.worker import main
        from kingdom.thread import create_thread

        thread_id = "council-sess"
        create_thread(project, BRANCH, thread_id, ["king", "claude", "codex", "cursor"], "council")

        with patch("kingdom.council.base.subprocess.Popen") as mock_cls:
            mock_cls.side_effect = lambda *a, **kw: mock_popen(stdout='{"result": "ok", "session_id": "sess-123"}\n')
            main(
                [
                    "--base",
                    str(project),
                    "--feature",
                    BRANCH,
                    "--thread-id",
                    thread_id,
                    "--prompt",
                    "session test",
                ]
            )

        # Sessions should have been saved
        state = get_agent_state(project, BRANCH, "claude")
        assert state.name == "claude"
