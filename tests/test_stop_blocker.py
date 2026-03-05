"""Tests for the Stop blocker's active-ticket gating.

The Stop hook should only block when there's an active ticket to log against.
When kd tk current --id fails or returns empty, Stop fails open (no block).
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from kingdom.cli.hook import (
    handle_post_tool_use,
    handle_stop,
    handle_user_prompt_submit,
)


class TestStopBlockerTicketGating:
    """Test Stop blocker respects active ticket state."""

    def setup_session(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_user_prompt_submit({"hook_event_name": "UserPromptSubmit", "session_id": session_id})

    def do_work(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            handle_post_tool_use(
                {"hook_event_name": "PostToolUse", "session_id": session_id, "tool_name": "Edit", "tool_input": {}}
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

    def stop(self, tmp_path: Path, session_id: str = "sess-1", stop_active: bool = False) -> str:
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(tmp_path)}):
            return handle_stop({"hook_event_name": "Stop", "session_id": session_id, "stop_hook_active": stop_active})

    # --- AC: no active ticket + had work => no block ---

    def test_no_active_ticket_passes_through(self, tmp_path: Path) -> None:
        """No active ticket + had_work + !did_log => no block."""
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with self.mock_kd_current(""):
            output = self.stop(tmp_path)
        assert output == ""

    # --- AC: active ticket + had work + no log => block with real ID ---

    def test_active_ticket_blocks_with_real_id(self, tmp_path: Path) -> None:
        """Active ticket + had_work + !did_log => block with concrete ticket ID."""
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with self.mock_kd_current("a1b2"):
            output = self.stop(tmp_path)
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log a1b2" in result["reason"]
        # No placeholder tokens.
        assert "<" not in result["reason"]

    # --- AC: kd tk current --id failure => fail open ---

    def test_kd_current_failure_fails_open(self, tmp_path: Path) -> None:
        """If kd tk current --id fails, Stop fails open."""
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with self.mock_kd_current(""):
            output = self.stop(tmp_path)
        assert output == ""

    # --- AC: mid-turn ticket create/accept => enforced at Stop time ---

    def test_mid_turn_ticket_accept_enforces_at_stop(self, tmp_path: Path) -> None:
        """Ticket created/accepted mid-turn => Stop resolves ticket at Stop time."""
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        with self.mock_kd_current("0240"):
            output = self.stop(tmp_path)
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "kd tk log 0240" in result["reason"]

    # --- Existing behaviors still work ---

    def test_stop_allows_when_did_log(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        self.do_work(tmp_path)
        self.do_log(tmp_path)
        output = self.stop(tmp_path)
        assert output == ""

    def test_stop_allows_when_no_work(self, tmp_path: Path) -> None:
        self.setup_session(tmp_path)
        output = self.stop(tmp_path)
        assert output == ""

    def test_missing_state_file_fails_open(self, tmp_path: Path) -> None:
        output = self.stop(tmp_path)
        assert output == ""
