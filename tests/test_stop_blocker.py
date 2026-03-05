"""Tests for the Stop blocker's active-ticket gating.

The Stop hook should only block when there's an active ticket to log against.
When kd tk current --id fails or returns empty, Stop fails open (no block).
"""

import json
import os
import subprocess
from pathlib import Path


class TestStopBlockerTicketGating:
    """Test Stop blocker respects active ticket state."""

    hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "kd-workflow.sh"

    def run_hook(
        self,
        tmp_path: Path,
        payload: dict,
        *,
        bypass: bool = False,
        kd_ticket_id: str | None = None,
    ) -> subprocess.CompletedProcess:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
        if bypass:
            env["KD_HOOK_BYPASS"] = "1"
        if kd_ticket_id is not None:
            mock_bin = tmp_path / "_mock_bin"
            mock_bin.mkdir(exist_ok=True)
            mock_kd = mock_bin / "kd"
            if kd_ticket_id:
                mock_kd.write_text(f'#!/bin/sh\necho "{kd_ticket_id}"\n')
            else:
                mock_kd.write_text("#!/bin/sh\nexit 1\n")
            mock_kd.chmod(0o755)
            env["PATH"] = f"{mock_bin}:{env.get('PATH', '')}"
        return subprocess.run(
            [str(self.hook_path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

    def submit(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        self.run_hook(tmp_path, {"hook_event_name": "UserPromptSubmit", "session_id": session_id})

    def tool_use(self, tmp_path: Path, tool: str, session_id: str = "sess-1", command: str = "") -> None:
        payload = {"hook_event_name": "PostToolUse", "session_id": session_id, "tool_name": tool, "tool_input": {}}
        if command:
            payload["tool_input"]["command"] = command
        self.run_hook(tmp_path, payload)

    def stop(
        self, tmp_path: Path, session_id: str = "sess-1", stop_active: bool = False, **kw
    ) -> subprocess.CompletedProcess:
        payload = {"hook_event_name": "Stop", "session_id": session_id, "stop_hook_active": stop_active}
        return self.run_hook(tmp_path, payload, **kw)

    # --- AC: no active ticket + had work => no block ---

    def test_no_active_ticket_passes_through(self, tmp_path: Path) -> None:
        """No active ticket + had_work + !did_log => no block."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, kd_ticket_id="")
        assert result.returncode == 0
        assert result.stdout.strip() == "" or "block" not in result.stdout

    # --- AC: active ticket + had work + no log => block with real ID ---

    def test_active_ticket_blocks_with_real_id(self, tmp_path: Path) -> None:
        """Active ticket + had_work + !did_log => block with concrete ticket ID."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, kd_ticket_id="a1b2")
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "kd tk log a1b2" in output["reason"]
        # No placeholder tokens.
        assert "<" not in output["reason"]

    # --- AC: kd tk current --id failure => fail open ---

    def test_kd_current_failure_fails_open(self, tmp_path: Path) -> None:
        """If kd tk current --id fails, Stop fails open."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, kd_ticket_id="")
        assert result.returncode == 0
        assert result.stdout.strip() == "" or "block" not in result.stdout

    # --- AC: mid-turn ticket create/accept => enforced at Stop time ---

    def test_mid_turn_ticket_accept_enforces_at_stop(self, tmp_path: Path) -> None:
        """Ticket created/accepted mid-turn => Stop resolves ticket at Stop time."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        # At stop time, kd tk current --id returns the newly created ticket.
        result = self.stop(tmp_path, kd_ticket_id="0240")
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "kd tk log 0240" in output["reason"]

    # --- Existing behaviors still work ---

    def test_stop_allows_when_did_log(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        self.tool_use(tmp_path, "Bash", command='kd tk log d4fc "summary"')
        result = self.stop(tmp_path, kd_ticket_id="d4fc")
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_stop_allows_when_no_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        result = self.stop(tmp_path, kd_ticket_id="0042")
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_missing_state_file_fails_open(self, tmp_path: Path) -> None:
        result = self.stop(tmp_path, kd_ticket_id="0042")
        assert result.returncode == 0
        assert result.stdout.strip() == "" or "block" not in result.stdout
