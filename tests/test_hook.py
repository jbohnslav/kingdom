"""Tests for kd hook run — event handlers and CLI integration."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.hook import (
    checkpoint_state_file,
    handle_post_compact,
    handle_post_tool_use,
    handle_pre_compact,
    handle_session_end,
    handle_session_start,
    handle_stop,
    handle_subagent_start,
    handle_subagent_stop,
    handle_user_prompt_submit,
    read_turn_state,
    state_file_for,
    write_turn_state,
)
from kingdom.lifecycle import Host, normalize_host_event
from kingdom.state import (
    backlog_root,
    compact_context_id,
    ensure_branch_layout,
    list_execution_contexts,
    read_execution_ticket_context,
    record_execution_ticket_context,
    record_terminal_ticket_context,
    resolve_execution_context,
    set_current_run,
)
from kingdom.ticket import Ticket, read_ticket, write_ticket

runner = CliRunner()


class TestSubagentLifecycle:
    def setup_parent(self, tmp_path: Path) -> tuple:
        feature = "feature/native-agents"
        branch = ensure_branch_layout(tmp_path, feature)
        set_current_run(tmp_path, feature)
        parent = resolve_execution_context(host="codex", session_id="parent-session", cwd=tmp_path)
        assert parent is not None
        ticket = Ticket(
            id="aaaa",
            status="in_progress",
            title="Owner ticket",
            assignee=parent.context_id,
        )
        path = branch / "tickets" / "aaaa.md"
        write_ticket(ticket, path)
        record_execution_ticket_context(tmp_path, parent, ticket.id, feature=feature)
        return parent, path

    def event(self, tmp_path: Path, name: str, **extra: str):
        payload = {
            "hook_event_name": name,
            "session_id": "parent-session",
            "cwd": str(tmp_path),
            "agent_id": "child-1",
            "agent_type": "explorer",
            **extra,
        }
        event = normalize_host_event(Host.CODEX, payload)
        assert event is not None
        return event

    def test_subagent_inherits_parent_ticket_without_taking_ownership(self, tmp_path: Path) -> None:
        parent, ticket_path = self.setup_parent(tmp_path)

        output = json.loads(handle_subagent_start(self.event(tmp_path, "SubagentStart")))

        child = resolve_execution_context(
            host="codex",
            session_id="child-1",
            role="subagent",
            parent_agent_id=parent.context_id,
            agent_type="explorer",
            cwd=tmp_path,
        )
        assert child is not None
        binding = read_execution_ticket_context(tmp_path, child)
        assert binding is not None
        assert binding["ticket_id"] == "aaaa"
        assert binding["parent_agent_id"] == parent.context_id
        assert binding["agent_type"] == "explorer"
        assert read_ticket(ticket_path).assignee == parent.context_id
        assert "inherit Kingdom ticket aaaa" in output["hookSpecificOutput"]["additionalContext"]

    def test_explicit_subagent_ticket_is_assigned_to_child(self, tmp_path: Path) -> None:
        parent, _ = self.setup_parent(tmp_path)
        branch = ensure_branch_layout(tmp_path, "feature/native-agents")
        child_path = branch / "tickets" / "bbbb.md"
        write_ticket(Ticket(id="bbbb", status="open", title="Child ticket"), child_path)

        handle_subagent_start(self.event(tmp_path, "SubagentStart", ticket_id="bbbb"))

        child = resolve_execution_context(
            host="codex",
            session_id="child-1",
            role="subagent",
            parent_agent_id=parent.context_id,
            agent_type="explorer",
            cwd=tmp_path,
        )
        assert child is not None
        ticket = read_ticket(child_path)
        assert ticket.status == "in_progress"
        assert ticket.assignee == child.context_id
        assert read_execution_ticket_context(tmp_path, child)["ticket_id"] == "bbbb"

    def test_subagent_stop_appends_handoff_and_marks_child_complete(self, tmp_path: Path) -> None:
        parent, ticket_path = self.setup_parent(tmp_path)
        handle_subagent_start(self.event(tmp_path, "SubagentStart"))

        assert handle_subagent_stop(self.event(tmp_path, "SubagentStop")) == ""

        child = resolve_execution_context(
            host="codex",
            session_id="child-1",
            role="subagent",
            parent_agent_id=parent.context_id,
            agent_type="explorer",
            cwd=tmp_path,
        )
        assert child is not None
        content = ticket_path.read_text(encoding="utf-8")
        assert f"[{compact_context_id(child.context_id)}]" in content
        assert "Native subagent explorer completed" in content
        context = next(item for item in list_execution_contexts(tmp_path) if item["context_id"] == child.context_id)
        assert context["active"] is False
        assert read_ticket(ticket_path).status == "in_progress"

    def test_missing_parent_binding_prompts_for_explicit_start_without_guessing(self, tmp_path: Path) -> None:
        ensure_branch_layout(tmp_path, "feature/native-agents")
        set_current_run(tmp_path, "feature/native-agents")

        output = json.loads(handle_subagent_start(self.event(tmp_path, "SubagentStart")))

        assert "kd tk start <id>" in output["hookSpecificOutput"]["additionalContext"]
        assert list_execution_contexts(tmp_path) == []


class TestCursorHookAdapter:
    def setup_binding(self, tmp_path: Path, session_id: str = "cursor-parent") -> tuple:
        feature = "feature/cursor-hooks"
        branch = ensure_branch_layout(tmp_path, feature)
        set_current_run(tmp_path, feature)
        context = resolve_execution_context(host="cursor", session_id=session_id, cwd=tmp_path)
        assert context is not None
        ticket = Ticket(id="cafe", status="in_progress", title="Cursor ticket", assignee=context.context_id)
        ticket_path = branch / "tickets" / "cafe.md"
        write_ticket(ticket, ticket_path)
        record_execution_ticket_context(tmp_path, context, ticket.id, feature=feature)
        return context, ticket_path

    def event(self, tmp_path: Path, name: str, **extra: object):
        event = normalize_host_event(
            Host.CURSOR,
            {
                "hook_event_name": name,
                "conversation_id": "cursor-parent",
                "workspace_roots": [str(tmp_path)],
                **extra,
            },
        )
        assert event is not None
        return event

    def test_session_start_uses_cursor_output_schema(self, tmp_path: Path) -> None:
        output = json.loads(handle_session_start(self.event(tmp_path, "sessionStart", session_id="cursor-parent")))

        assert "KINGDOM WORKFLOW" in output["additional_context"]
        assert output["env"] == {"KD_CONTEXT": "cursor-parent", "KD_HOST": "cursor"}
        assert "hookSpecificOutput" not in output

    def test_prompt_submit_allows_without_claiming_context_injection(self, tmp_path: Path) -> None:
        output = json.loads(handle_user_prompt_submit(self.event(tmp_path, "beforeSubmitPrompt")))

        assert output == {"continue": True}

    def test_pre_compact_uses_cursor_user_message(self, tmp_path: Path) -> None:
        self.setup_binding(tmp_path)

        output = json.loads(handle_pre_compact(self.event(tmp_path, "preCompact", trigger="auto")))

        assert "ticket cafe" in output["user_message"]
        assert "systemMessage" not in output

    def test_subagent_start_records_stable_child_and_allows_spawn(self, tmp_path: Path) -> None:
        parent, ticket_path = self.setup_binding(tmp_path)

        output = json.loads(
            handle_subagent_start(
                self.event(
                    tmp_path,
                    "subagentStart",
                    subagent_id="cursor-child",
                    subagent_type="explore",
                    parent_conversation_id="cursor-parent",
                )
            )
        )

        child = resolve_execution_context(
            host="cursor",
            session_id="cursor-child",
            role="subagent",
            parent_agent_id=parent.context_id,
            agent_type="explore",
            cwd=tmp_path,
        )
        assert child is not None
        assert read_execution_ticket_context(tmp_path, child)["ticket_id"] == "cafe"
        assert read_ticket(ticket_path).assignee == parent.context_id
        assert output == {"permission": "allow"}

    def test_stop_uses_exact_cursor_binding_and_followup_schema(self, tmp_path: Path) -> None:
        self.setup_binding(tmp_path)
        handle_user_prompt_submit(self.event(tmp_path, "beforeSubmitPrompt"))
        handle_post_tool_use(self.event(tmp_path, "postToolUse", tool_name="Edit", tool_input={}))

        output = json.loads(handle_stop(self.event(tmp_path, "stop", status="completed", loop_count=0)))

        assert "kd tk log cafe" in output["followup_message"]
        assert "decision" not in output


class TestTicketCheckpoints:
    def setup_binding(self, tmp_path: Path, ticket_id: str = "aaaa") -> Path:
        feature = "feature/checkpoint"
        branch = ensure_branch_layout(tmp_path, feature)
        set_current_run(tmp_path, feature)
        context = resolve_execution_context(host="codex", session_id="session-1", cwd=tmp_path)
        assert context is not None
        path = branch / "tickets" / f"{ticket_id}.md"
        write_ticket(Ticket(id=ticket_id, status="in_progress", title="Checkpoint", assignee=context.context_id), path)
        record_execution_ticket_context(tmp_path, context, ticket_id, feature=feature)
        return path

    def event(self, tmp_path: Path, name: str, **extra: str):
        event = normalize_host_event(
            Host.CODEX,
            {
                "hook_event_name": name,
                "session_id": "session-1",
                "cwd": str(tmp_path),
                **extra,
            },
        )
        assert event is not None
        return event

    def test_pre_compact_requests_structured_exact_ticket_checkpoint(self, tmp_path: Path) -> None:
        self.setup_binding(tmp_path)
        other = ensure_branch_layout(tmp_path, "feature/checkpoint") / "tickets" / "bbbb.md"
        write_ticket(Ticket(id="bbbb", status="in_progress", title="Unrelated recent ticket"), other)

        output = json.loads(handle_pre_compact(self.event(tmp_path, "PreCompact", trigger="auto")))

        message = output["systemMessage"]
        assert "ticket aaaa" in message
        assert "bbbb" not in message
        assert "decisions" in message
        assert "verification" in message
        assert "blockers" in message
        assert "next steps" in message

    def test_repeated_checkpoint_is_idempotent_until_ticket_update(self, tmp_path: Path) -> None:
        ticket_path = self.setup_binding(tmp_path)
        event = self.event(tmp_path, "PreCompact", trigger="auto")

        assert handle_pre_compact(event)
        assert handle_pre_compact(event) == ""

        handle_post_tool_use(
            self.event(
                tmp_path,
                "PostToolUse",
                tool_name="Edit",
                tool_input={"file_path": str(ticket_path)},
            )
        )
        assert not checkpoint_state_file(tmp_path, "codex", "session-1").exists()
        assert handle_pre_compact(event)

    def test_post_compact_and_compact_resume_repeat_pending_request(self, tmp_path: Path) -> None:
        self.setup_binding(tmp_path)
        handle_pre_compact(self.event(tmp_path, "PreCompact", trigger="auto"))

        post = json.loads(handle_post_compact(self.event(tmp_path, "PostCompact", trigger="auto")))
        resumed = json.loads(handle_session_start(self.event(tmp_path, "SessionStart", source="compact")))

        assert "ticket aaaa" in post["systemMessage"]
        assert "ticket aaaa" in resumed["hookSpecificOutput"]["additionalContext"]

    def test_session_end_requests_same_handoff_without_blocking(self, tmp_path: Path) -> None:
        self.setup_binding(tmp_path)

        output = json.loads(handle_session_end(self.event(tmp_path, "SessionEnd", reason="other")))

        assert "ticket aaaa" in output["systemMessage"]
        assert "continue" not in output
        assert checkpoint_state_file(tmp_path, "codex", "session-1").exists()

    def test_missing_exact_binding_fails_open_without_branch_guess(self, tmp_path: Path) -> None:
        ensure_branch_layout(tmp_path, "feature/checkpoint")
        set_current_run(tmp_path, "feature/checkpoint")

        assert handle_pre_compact(self.event(tmp_path, "PreCompact", trigger="auto")) == ""


# ---------------------------------------------------------------------------
# SessionStart handler
# ---------------------------------------------------------------------------


class TestSessionStart:
    def test_emits_brief_as_additional_context(self) -> None:
        output = handle_session_start({"hook_event_name": "SessionStart", "session_id": "sess-1", "cwd": "/workspace"})
        parsed = json.loads(output)
        hso = parsed["hookSpecificOutput"]
        assert hso["hookEventName"] == "SessionStart"
        assert "KINGDOM WORKFLOW" in hso["additionalContext"]
        assert "TICKET FIRST" in hso["additionalContext"]
        assert "LOG PROACTIVELY" in hso["additionalContext"]
        assert "kd tk defer" in hso["additionalContext"]
        assert "kd tk move" not in hso["additionalContext"]

    def test_emits_on_resume(self) -> None:
        output = handle_session_start(
            {
                "hook_event_name": "SessionStart",
                "session_id": "sess-1",
                "cwd": "/workspace",
                "source": "resume",
            }
        )
        parsed = json.loads(output)
        assert "KINGDOM WORKFLOW" in parsed["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------------------
# UserPromptSubmit handler
# ---------------------------------------------------------------------------


class TestUserPromptSubmit:
    def test_emits_reminder_as_additional_context(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": "sess-1"})
        parsed = json.loads(output)
        hso = parsed["hookSpecificOutput"]
        assert hso["hookEventName"] == "UserPromptSubmit"
        assert "Kingdom:" in hso["additionalContext"]
        assert "kd tk create" in hso["additionalContext"]
        assert "kd tk defer" in hso["additionalContext"]
        assert "kd tk move" not in hso["additionalContext"]

    def test_creates_state_file(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": "sess-1"})
        sf = state_file_for(str(tmp_path), "sess-1")
        state = json.loads(sf.read_text())
        assert state == {"had_work": False, "did_log": False, "stop_blocked": False}

    def test_resets_state(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": "sess-1"})
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "Edit", "tool_input": {}}
            )
            sf = state_file_for(str(tmp_path), "sess-1")
            assert json.loads(sf.read_text())["had_work"] is True
            # New submit resets.
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": "sess-1"})
            assert json.loads(sf.read_text()) == {"had_work": False, "did_log": False, "stop_blocked": False}

    def test_accepts_normalized_event_with_claude_project_dir(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            event = normalize_host_event(
                Host.CLAUDE,
                {"hook_event_name": "UserPromptSubmit", "session_id": "sess-1"},
            )
            assert event is not None
            handle_user_prompt_submit(event)

        sf = state_file_for(str(tmp_path), "sess-1")
        assert json.loads(sf.read_text()) == {"had_work": False, "did_log": False, "stop_blocked": False}


# ---------------------------------------------------------------------------
# PostToolUse handler
# ---------------------------------------------------------------------------


class TestPostToolUse:
    def setup_session(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": session_id})

    def read_state(self, tmp_path: Path, session_id: str = "sess-1") -> dict:
        sf = state_file_for(str(tmp_path), session_id)
        return json.loads(sf.read_text())

    def test_edit_sets_had_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "Edit", "tool_input": {}}
            )
        assert self.read_state(tmp_path)["had_work"] is True

    def test_write_sets_had_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "Write", "tool_input": {}}
            )
        assert self.read_state(tmp_path)["had_work"] is True

    def test_web_search_sets_had_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "WebSearch", "tool_input": {}}
            )
        assert self.read_state(tmp_path)["had_work"] is True

    def test_web_fetch_sets_had_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "WebFetch", "tool_input": {}}
            )
        assert self.read_state(tmp_path)["had_work"] is True

    def test_read_does_not_set_had_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "Read", "tool_input": {}}
            )
        assert self.read_state(tmp_path)["had_work"] is False

    def test_bash_does_not_set_had_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "sess-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls -la"},
                }
            )
        assert self.read_state(tmp_path)["had_work"] is False

    def test_kd_tk_log_sets_did_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "sess-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": 'kd tk log d4fc "did stuff"'},
                }
            )
        assert self.read_state(tmp_path)["did_log"] is True

    def test_kd_ticket_log_sets_did_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "sess-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": 'kd ticket log d4fc "did stuff"'},
                }
            )
        assert self.read_state(tmp_path)["did_log"] is True

    def test_unrelated_bash_does_not_set_did_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "sess-1",
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest"},
                }
            )
        assert self.read_state(tmp_path)["did_log"] is False

    def test_no_session_id_silent(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_post_tool_use({"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {}})
        assert output == ""

    def test_no_state_file_fails_open(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-1", "tool_name": "Edit", "tool_input": {}}
            )
        assert output == ""


# ---------------------------------------------------------------------------
# Stop handler
# ---------------------------------------------------------------------------


class TestStopHandler:
    def create_ticket(
        self,
        tmp_path: Path,
        feature: str,
        ticket_id: str,
        *,
        status: str = "in_progress",
        assignee: str | None = None,
    ) -> None:
        branch_dir = ensure_branch_layout(tmp_path, feature)
        write_ticket(
            Ticket(id=ticket_id, status=status, title=f"Ticket {ticket_id}", body="", assignee=assignee),
            branch_dir / "tickets" / f"{ticket_id}.md",
        )

    def setup_session(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": session_id})

    def do_work(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": session_id, "tool_name": "Edit", "tool_input": {}}
            )

    def edit_path(self, tmp_path: Path, path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": session_id,
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(path)},
                }
            )

    def do_log(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": session_id,
                    "tool_name": "Bash",
                    "tool_input": {"command": 'kd tk log d4fc "summary"'},
                }
            )

    def mock_kd_current(self, ticket_id: str):
        """Mock subprocess.run for kd tk current --id."""
        from unittest.mock import MagicMock

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            if ticket_id:
                result.returncode = 0
                result.stdout = ticket_id + "\n"
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        return patch("kingdom.cli.hook.subprocess.run", side_effect=fake_run)

    def test_blocks_when_had_work_no_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current("0042"),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log 0042" in result["reason"]

    def test_ticket_markdown_only_edit_does_not_block(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        ticket_path = tmp_path / ".kd" / "branches" / "branch-a" / "tickets" / "7e15.md"
        self.edit_path(tmp_path, ticket_path)

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("7e15"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        assert output == ""

    def test_ticket_markdown_edit_counts_as_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        ticket_path = tmp_path / ".kd" / "branches" / "branch-a" / "tickets" / "7e15.md"
        code_path = tmp_path / "src" / "kingdom" / "cli" / "hook.py"
        self.edit_path(tmp_path, code_path)
        self.edit_path(tmp_path, ticket_path)

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("7e15"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        assert output == ""

    def test_prefers_terminal_last_started_ticket(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        self.create_ticket(tmp_path, "branch-a", "7e15")
        set_current_run(tmp_path, "branch-a")
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(tmp_path, "7e15", feature="branch-a")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        result = json.loads(output)
        assert "kd tk log 7e15" in result["reason"]
        assert "9999" not in result["reason"]

    def test_reads_terminal_ticket_context_from_kd_base(self, tmp_path: Path) -> None:
        kingdom_base = tmp_path / "main"
        worktree = tmp_path / "worktree"
        kingdom_base.mkdir()
        worktree.mkdir()

        self.setup_session(worktree)
        self.do_work(worktree)
        self.create_ticket(kingdom_base, "branch-a", "7e15")
        set_current_run(kingdom_base, "branch-a")
        env = {
            "CLAUDE_PROJECT_DIR": str(worktree),
            "KD_BASE": str(kingdom_base),
            "TERM_SESSION_ID": "terminal-a",
        }
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(kingdom_base, "7e15", feature="branch-a")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        result = json.loads(output)
        assert "kd tk log 7e15" in result["reason"]
        assert "9999" not in result["reason"]

    def test_prefers_started_backlog_ticket_context(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        backlog_tickets = backlog_root(tmp_path) / "tickets"
        backlog_tickets.mkdir(parents=True)
        write_ticket(
            Ticket(id="7e15", status="in_progress", title="Backlog ticket", body=""),
            backlog_tickets / "7e15.md",
        )
        ensure_branch_layout(tmp_path, "branch-a")
        set_current_run(tmp_path, "branch-a")
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(tmp_path, "7e15", feature="branch-a", location="backlog")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        result = json.loads(output)
        assert "kd tk log 7e15" in result["reason"]
        assert "9999" not in result["reason"]

    def test_prefers_started_archived_branch_ticket_context(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        archived_tickets = tmp_path / ".kd" / "archive" / "old-feature" / "tickets"
        archived_tickets.mkdir(parents=True)
        write_ticket(
            Ticket(id="7e15", status="in_progress", title="Archived branch ticket", body=""),
            archived_tickets / "7e15.md",
        )
        ensure_branch_layout(tmp_path, "branch-a")
        set_current_run(tmp_path, "branch-a")
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(tmp_path, "7e15", feature="branch-a", location="archive:old-feature")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        result = json.loads(output)
        assert "kd tk log 7e15" in result["reason"]
        assert "9999" not in result["reason"]

    def test_ignores_closed_terminal_ticket_context(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        self.create_ticket(tmp_path, "branch-a", "7e15", status="closed")
        set_current_run(tmp_path, "branch-a")
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(tmp_path, "7e15", feature="branch-a")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_ignores_peasant_terminal_ticket_context(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        self.create_ticket(tmp_path, "branch-a", "7e15", assignee="peasant-7e15")
        set_current_run(tmp_path, "branch-a")
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(tmp_path, "7e15", feature="branch-a")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_ignores_terminal_ticket_context_from_other_feature(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        self.create_ticket(tmp_path, "branch-a", "7e15")
        ensure_branch_layout(tmp_path, "branch-b")
        set_current_run(tmp_path, "branch-b")
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}
        with patch.dict(os.environ, env):
            record_terminal_ticket_context(tmp_path, "7e15", feature="branch-a")

        with patch.dict(os.environ, env), self.mock_kd_current("9999"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_terminal_ticket_context_is_isolated(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path, session_id="sess-a")
        self.setup_session(tmp_path, session_id="sess-b")
        self.do_work(tmp_path, session_id="sess-a")
        self.do_work(tmp_path, session_id="sess-b")
        self.create_ticket(tmp_path, "branch-a", "aaaa")
        self.create_ticket(tmp_path, "branch-b", "bbbb")
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}):
            record_terminal_ticket_context(tmp_path, "aaaa", feature="branch-a")
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-b"}):
            record_terminal_ticket_context(tmp_path, "bbbb", feature="branch-b")

        set_current_run(tmp_path, "branch-a")
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-a"}):
            output_a = handle_stop({"hook_event_name": "Stop", "session_id": "sess-a", "stop_hook_active": False})
        set_current_run(tmp_path, "branch-b")
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path), "TERM_SESSION_ID": "terminal-b"}):
            output_b = handle_stop({"hook_event_name": "Stop", "session_id": "sess-b", "stop_hook_active": False})

        assert "kd tk log aaaa" in json.loads(output_a)["reason"]
        assert "kd tk log bbbb" in json.loads(output_b)["reason"]

    def test_allows_when_did_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        self.do_log(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_allows_when_no_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_allows_when_stop_hook_active(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": True})
        assert output == ""

    def test_no_state_file_fails_open(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_no_active_ticket_passes_through(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current(""):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_active_ticket_blocks_with_real_id(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current("a1b2"),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log a1b2" in result["reason"]
        assert "<" not in result["reason"]

    def test_kd_current_failure_fails_open(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current(""),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_kd_current_exception_fails_open(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            patch("kingdom.cli.hook.subprocess.run", side_effect=Exception("timeout")),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_mid_turn_ticket_accept_enforces_at_stop(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current("0240"),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log 0240" in result["reason"]

    def test_explicit_legacy_fallback_uses_kd_current(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)

        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current("9999"),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        result = json.loads(output)
        assert "kd tk log 9999" in result["reason"]

    def test_second_stop_same_turn_does_not_loop(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)

        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current("0042"),
        ):
            first_output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
            second_output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        assert json.loads(first_output)["decision"] == "block"
        assert second_output == ""

    # --- Multi-agent isolation ---

    def test_separate_sessions_no_cross_blocking(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path, session_id="sess-a")
        self.setup_session(tmp_path, session_id="sess-b")
        self.do_work(tmp_path, session_id="sess-a")
        # Session B's Stop should not block.
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output_b = handle_stop({"hook_event_name": "Stop", "session_id": "sess-b", "stop_hook_active": False})
        assert output_b == ""
        # Session A's Stop should block.
        with (
            patch.dict(
                os.environ,
                {"CLAUDE_PROJECT_DIR": str(tmp_path), "KD_HOOK_LEGACY_TICKET_FALLBACK": "1"},
            ),
            self.mock_kd_current("0099"),
        ):
            output_a = handle_stop({"hook_event_name": "Stop", "session_id": "sess-a", "stop_hook_active": False})
        result = json.loads(output_a)
        assert result["decision"] == "block"

    def test_sessions_have_independent_state(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path, session_id="sess-a")
        self.setup_session(tmp_path, session_id="sess-b")
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": "sess-a", "tool_name": "Write", "tool_input": {}}
            )
            handle_post_tool_use(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "sess-b",
                    "tool_name": "Bash",
                    "tool_input": {"command": 'kd tk log x "y"'},
                }
            )
        sf_a = state_file_for(str(tmp_path), "sess-a")
        sf_b = state_file_for(str(tmp_path), "sess-b")
        assert json.loads(sf_a.read_text()) == {"had_work": True, "did_log": False, "stop_blocked": False}
        assert json.loads(sf_b.read_text()) == {"had_work": False, "did_log": True, "stop_blocked": False}

    def test_stale_state_does_not_block_new_session(self, tmp_path: Path) -> None:
        runtime = tmp_path / ".kd" / "runtime"
        runtime.mkdir(parents=True)
        stale = runtime / "turn-old-session.json"
        stale.write_text(json.dumps({"had_work": True, "did_log": False}))
        self.setup_session(tmp_path, session_id="new-session")
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "new-session", "stop_hook_active": False})
        assert output == ""


# ---------------------------------------------------------------------------
# CLI integration — kd hook run
# ---------------------------------------------------------------------------


class TestHookRunCLI:
    """Test the kd hook run command via CLI runner."""

    def test_session_start_via_cli(self) -> None:
        result = runner.invoke(
            app,
            ["hook", "run", "--host", "claude"],
            input='{"hook_event_name":"SessionStart","session_id":"s1","cwd":"/workspace"}',
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output.strip())
        assert "KINGDOM WORKFLOW" in parsed["hookSpecificOutput"]["additionalContext"]

    def test_user_prompt_submit_via_cli(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["hook", "run", "--host", "claude"],
            input=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "s1",
                    "cwd": str(tmp_path),
                }
            ),
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output.strip())
        assert "Kingdom:" in parsed["hookSpecificOutput"]["additionalContext"]

    def test_unknown_event_silent(self) -> None:
        result = runner.invoke(app, ["hook", "run"], input='{"hook_event_name": "Notification"}')
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_empty_input_silent(self) -> None:
        result = runner.invoke(app, ["hook", "run"], input="{}")
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_bypass_skips_all(self) -> None:
        with patch.dict(os.environ, {"KD_HOOK_BYPASS": "1"}):
            result = runner.invoke(app, ["hook", "run"], input='{"hook_event_name": "SessionStart"}')
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_bad_json_fails_open(self) -> None:
        result = runner.invoke(app, ["hook", "run"], input="not json at all")
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_stop_no_state_via_cli(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            result = runner.invoke(
                app,
                ["hook", "run"],
                input='{"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": false}',
            )
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_supported_observational_lifecycle_events_are_silent(self, tmp_path: Path) -> None:
        for event_name in ("SessionEnd", "PreCompact", "PostCompact", "SubagentStop"):
            payload: dict[str, object] = {
                "hook_event_name": event_name,
                "session_id": "s1",
                "cwd": str(tmp_path),
            }
            if event_name.startswith("Subagent"):
                payload["subagent_id"] = "child-1"

            result = runner.invoke(app, ["hook", "run", "--host", "claude"], input=json.dumps(payload))
            assert result.exit_code == 0
            assert result.output.strip() == ""

    def test_subagent_start_explains_missing_parent_binding(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["hook", "run", "--host", "claude"],
            input=json.dumps(
                {
                    "hook_event_name": "SubagentStart",
                    "session_id": "s1",
                    "subagent_id": "child-1",
                    "cwd": str(tmp_path),
                }
            ),
        )

        assert result.exit_code == 0
        assert "kd start" in json.loads(result.output)["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------------------
# Turn-state helpers
# ---------------------------------------------------------------------------


class TestTurnStateHelpers:
    def test_read_turn_state_missing(self, tmp_path: Path) -> None:
        assert read_turn_state(tmp_path / "nope.json") is None

    def test_read_turn_state_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "state.json"
        f.write_text('{"had_work": true, "did_log": false}')
        assert read_turn_state(f) == {"had_work": True, "did_log": False}

    def test_read_turn_state_corrupt(self, tmp_path: Path) -> None:
        f = tmp_path / "state.json"
        f.write_text("not json")
        assert read_turn_state(f) is None

    def test_write_turn_state(self, tmp_path: Path) -> None:
        f = tmp_path / "state.json"
        write_turn_state(f, {"had_work": False, "did_log": True})
        assert json.loads(f.read_text()) == {"had_work": False, "did_log": True}
