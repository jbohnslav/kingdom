"""Tests for kd hook run — event handlers and CLI integration."""

import json
import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.hook import (
    handle_post_tool_use,
    handle_session_start,
    handle_stop,
    handle_user_prompt_submit,
    read_turn_state,
    state_file_for,
    write_turn_state,
)
from kingdom.state import backlog_root, ensure_branch_layout, record_terminal_ticket_context, set_current_run
from kingdom.ticket import Ticket, write_ticket

runner = CliRunner()


# ---------------------------------------------------------------------------
# SessionStart handler
# ---------------------------------------------------------------------------


class TestSessionStart:
    def test_emits_brief_as_additional_context(self) -> None:
        output = handle_session_start({"hook_event_name": "SessionStart"})
        parsed = json.loads(output)
        hso = parsed["hookSpecificOutput"]
        assert hso["hookEventName"] == "SessionStart"
        assert "KINGDOM WORKFLOW" in hso["additionalContext"]
        assert "TICKET FIRST" in hso["additionalContext"]
        assert "LOG PROACTIVELY" in hso["additionalContext"]

    def test_emits_on_resume(self) -> None:
        output = handle_session_start({"hook_event_name": "SessionStart", "source": "resume"})
        parsed = json.loads(output)
        assert "KINGDOM WORKFLOW" in parsed["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------------------
# UserPromptSubmit handler
# ---------------------------------------------------------------------------


class TestUserPromptSubmit:
    def test_emits_reminder_as_additional_context(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            output = handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit"})
        parsed = json.loads(output)
        hso = parsed["hookSpecificOutput"]
        assert hso["hookEventName"] == "UserPromptSubmit"
        assert "Kingdom:" in hso["additionalContext"]
        assert "kd tk create" in hso["additionalContext"]

    def test_creates_state_file(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": "sess-1"})
        sf = state_file_for(str(tmp_path), "sess-1")
        state = json.loads(sf.read_text())
        assert state == {"had_work": False, "did_log": False}

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
            assert json.loads(sf.read_text()) == {"had_work": False, "did_log": False}


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
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("0042"):
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

    def test_mixed_ticket_and_code_edit_still_blocks(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        ticket_path = tmp_path / ".kd" / "branches" / "branch-a" / "tickets" / "7e15.md"
        code_path = tmp_path / "src" / "kingdom" / "cli" / "hook.py"
        self.edit_path(tmp_path, ticket_path)
        self.edit_path(tmp_path, code_path)

        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("7e15"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})

        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log 7e15" in result["reason"]

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

        result = json.loads(output)
        assert "kd tk log 9999" in result["reason"]
        assert "7e15" not in result["reason"]

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

        result = json.loads(output)
        assert "kd tk log 9999" in result["reason"]
        assert "7e15" not in result["reason"]

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

        result = json.loads(output)
        assert "kd tk log 9999" in result["reason"]
        assert "7e15" not in result["reason"]

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
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("a1b2"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log a1b2" in result["reason"]
        assert "<" not in result["reason"]

    def test_kd_current_failure_fails_open(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current(""):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_kd_current_exception_fails_open(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with (
            patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}),
            patch("kingdom.cli.hook.subprocess.run", side_effect=Exception("timeout")),
        ):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        assert output == ""

    def test_mid_turn_ticket_accept_enforces_at_stop(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("0240"):
            output = handle_stop({"hook_event_name": "Stop", "session_id": "sess-1", "stop_hook_active": False})
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log 0240" in result["reason"]

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
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}), self.mock_kd_current("0099"):
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
        assert json.loads(sf_a.read_text()) == {"had_work": True, "did_log": False}
        assert json.loads(sf_b.read_text()) == {"had_work": False, "did_log": True}

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
        result = runner.invoke(app, ["hook", "run"], input='{"hook_event_name": "SessionStart"}')
        assert result.exit_code == 0
        parsed = json.loads(result.output.strip())
        assert "KINGDOM WORKFLOW" in parsed["hookSpecificOutput"]["additionalContext"]

    def test_user_prompt_submit_via_cli(self) -> None:
        result = runner.invoke(app, ["hook", "run"], input='{"hook_event_name": "UserPromptSubmit"}')
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
