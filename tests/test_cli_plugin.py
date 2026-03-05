"""Tests for kd plugin enable/disable/status commands."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.plugin import (
    HOOK_CONFIG,
    HOOK_EVENTS,
    has_hook_for_event,
    is_hook_installed,
    read_settings,
    write_settings,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestReadWriteSettings:
    def test_read_missing_file(self, tmp_path: Path) -> None:
        assert read_settings(tmp_path / "nope.json") == {}

    def test_read_existing_file(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        p.write_text('{"foo": 1}')
        assert read_settings(p) == {"foo": 1}

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        p = tmp_path / "a" / "b" / "settings.json"
        write_settings(p, {"x": 1})
        assert p.exists()
        assert json.loads(p.read_text()) == {"x": 1}

    def test_roundtrip(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        data = {"hooks": {event: [HOOK_CONFIG] for event in HOOK_EVENTS}}
        write_settings(p, data)
        assert read_settings(p) == data


class TestIsHookInstalled:
    def test_empty_settings(self) -> None:
        assert not is_hook_installed({})

    def test_no_hooks(self) -> None:
        assert not is_hook_installed({"hooks": {}})

    def test_only_user_prompt_submit_hook(self) -> None:
        settings = {"hooks": {"UserPromptSubmit": [HOOK_CONFIG]}}
        assert not is_hook_installed(settings)

    def test_only_session_start_hook(self) -> None:
        settings = {"hooks": {"SessionStart": [HOOK_CONFIG]}}
        assert not is_hook_installed(settings)

    def test_missing_one_event(self) -> None:
        settings = {
            "hooks": {"SessionStart": [HOOK_CONFIG], "UserPromptSubmit": [HOOK_CONFIG], "PostToolUse": [HOOK_CONFIG]}
        }
        assert not is_hook_installed(settings)

    def test_all_hooks_present(self) -> None:
        settings = {"hooks": {event: [HOOK_CONFIG] for event in HOOK_EVENTS}}
        assert is_hook_installed(settings)

    def test_other_hooks_only(self) -> None:
        settings = {
            "hooks": {"UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}]}
        }
        assert not is_hook_installed(settings)

    def test_kingdom_hook_among_others(self) -> None:
        other = {"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}
        settings = {"hooks": {event: [HOOK_CONFIG] for event in HOOK_EVENTS}}
        settings["hooks"]["UserPromptSubmit"] = [other, HOOK_CONFIG]
        assert is_hook_installed(settings)


class TestHasHookForEvent:
    def test_missing_event(self) -> None:
        assert not has_hook_for_event({}, "UserPromptSubmit")

    def test_present(self) -> None:
        assert has_hook_for_event({"hooks": {"UserPromptSubmit": [HOOK_CONFIG]}}, "UserPromptSubmit")


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def mock_git_root(tmp_path: Path):
    """Patch find_git_root to return tmp_path."""
    return patch("kingdom.cli.plugin.find_git_root", return_value=tmp_path)


class TestPluginEnable:
    def test_enable_creates_settings(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "enabled" in result.output

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert is_hook_installed(settings)

    def test_enable_installs_both_hooks(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event in HOOK_EVENTS:
            assert has_hook_for_event(settings, event), f"Missing hook for {event}"

    def test_enable_preserves_existing_settings(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text('{"permissions": {"allow": ["Bash(git:*)"]}}')

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0

        settings = json.loads(settings_path.read_text())
        assert settings["permissions"] == {"allow": ["Bash(git:*)"]}
        assert is_hook_installed(settings)

    def test_enable_idempotent(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "already enabled" in result.output

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event in HOOK_EVENTS:
            assert len(settings["hooks"][event]) == 1

    def test_enable_adds_missing_events(self, tmp_path: Path) -> None:
        """If only some events are present, enable adds the missing ones."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({"hooks": {"UserPromptSubmit": [HOOK_CONFIG]}}))

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "enable"])
        assert result.exit_code == 0
        assert "enabled" in result.output

        settings = json.loads(settings_path.read_text())
        assert is_hook_installed(settings)
        # UserPromptSubmit should still only have one entry
        assert len(settings["hooks"]["UserPromptSubmit"]) == 1


class TestPluginDisable:
    def test_disable_removes_hook(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])
            result = runner.invoke(app, ["plugin", "disable"])
        assert result.exit_code == 0
        assert "disabled" in result.output

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert not is_hook_installed(settings)
        assert "hooks" not in settings

    def test_disable_preserves_other_hooks(self, tmp_path: Path) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        other_hook = {"matcher": "", "hooks": [{"type": "command", "command": "other.sh"}]}
        hooks = {event: [HOOK_CONFIG] for event in HOOK_EVENTS}
        hooks["UserPromptSubmit"] = [other_hook, HOOK_CONFIG]
        settings_path.write_text(json.dumps({"hooks": hooks}))

        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "disable"])
        assert result.exit_code == 0

        settings = json.loads(settings_path.read_text())
        assert "SessionStart" not in settings["hooks"]
        assert "PostToolUse" not in settings["hooks"]
        assert "Stop" not in settings["hooks"]
        assert len(settings["hooks"]["UserPromptSubmit"]) == 1
        assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "other.sh"

    def test_disable_when_not_enabled(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "disable"])
        assert result.exit_code == 0
        assert "not enabled" in result.output


class TestPluginStatus:
    def test_status_enabled(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            runner.invoke(app, ["plugin", "enable"])
            result = runner.invoke(app, ["plugin", "status"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_status_disabled(self, tmp_path: Path) -> None:
        with mock_git_root(tmp_path):
            result = runner.invoke(app, ["plugin", "status"])
        assert result.exit_code == 0
        assert "disabled" in result.output


# ---------------------------------------------------------------------------
# Hook script tests
# ---------------------------------------------------------------------------


class TestHookScript:
    """Test the hook shell script behavior."""

    hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "kd-workflow.sh"

    def test_session_start_emits_brief(self) -> None:
        result = subprocess.run(
            [str(self.hook_path)],
            input='{"hook_event_name": "SessionStart", "source": "startup"}',
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "KINGDOM WORKFLOW" in result.stdout
        assert "TICKET FIRST" in result.stdout
        assert "LOG PROACTIVELY" in result.stdout

    def test_session_start_resume(self) -> None:
        result = subprocess.run(
            [str(self.hook_path)],
            input='{"hook_event_name": "SessionStart", "source": "resume"}',
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "KINGDOM WORKFLOW" in result.stdout

    def test_user_prompt_submit_emits_reminder(self) -> None:
        result = subprocess.run(
            [str(self.hook_path)],
            input='{"hook_event_name": "UserPromptSubmit"}',
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "Kingdom:" in result.stdout
        assert "kd tk create" in result.stdout

    def test_stop_no_state_fails_open(self, tmp_path: Path) -> None:
        """Stop with no state file should not block (fail-open)."""
        env = {**subprocess.os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
        result = subprocess.run(
            [str(self.hook_path)],
            input='{"hook_event_name": "Stop", "stop_hook_active": false}',
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_unknown_event_silent(self) -> None:
        result = subprocess.run(
            [str(self.hook_path)],
            input='{"hook_event_name": "Notification"}',
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_empty_input_silent(self) -> None:
        result = subprocess.run(
            [str(self.hook_path)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert result.stdout == ""


# ---------------------------------------------------------------------------
# V2 blocker tests
# ---------------------------------------------------------------------------


class TestV2Blocker:
    """Test the stateful Stop blocker lifecycle."""

    hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "kd-workflow.sh"

    def run_hook(
        self,
        tmp_path: Path,
        payload: dict,
        *,
        bypass: bool = False,
        kd_ticket_id: str | None = None,
    ) -> subprocess.CompletedProcess:
        env = {**subprocess.os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
        if bypass:
            env["KD_HOOK_BYPASS"] = "1"
        if kd_ticket_id is not None:
            # Create a mock kd script that returns the given ticket ID (or fails if empty).
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
            timeout=5,
            env=env,
        )

    def state_file(self, tmp_path: Path, session_id: str) -> Path:
        return tmp_path / ".kd" / "runtime" / f"turn-{session_id}.json"

    def read_state(self, tmp_path: Path, session_id: str) -> dict:
        return json.loads(self.state_file(tmp_path, session_id).read_text())

    def submit(self, tmp_path: Path, session_id: str = "sess-1") -> None:
        self.run_hook(tmp_path, {"hook_event_name": "UserPromptSubmit", "session_id": session_id})

    def tool_use(self, tmp_path: Path, tool: str, session_id: str = "sess-1", command: str = "") -> None:
        payload = {"hook_event_name": "PostToolUse", "session_id": session_id, "tool_name": tool, "tool_input": {}}
        if command:
            payload["tool_input"]["command"] = command
        self.run_hook(tmp_path, payload)

    def stop(
        self,
        tmp_path: Path,
        session_id: str = "sess-1",
        stop_active: bool = False,
        **kw,
    ) -> subprocess.CompletedProcess:
        payload = {"hook_event_name": "Stop", "session_id": session_id, "stop_hook_active": stop_active}
        return self.run_hook(tmp_path, payload, **kw)

    # --- UserPromptSubmit creates/resets state ---

    def test_submit_creates_state_file(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        state = self.read_state(tmp_path, "sess-1")
        assert state == {"had_work": False, "did_log": False}

    def test_submit_resets_state(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is True
        # New submit resets.
        self.submit(tmp_path)
        assert self.read_state(tmp_path, "sess-1") == {"had_work": False, "did_log": False}

    # --- PostToolUse tracking ---

    def test_edit_sets_had_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is True

    def test_write_sets_had_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Write")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is True

    def test_web_search_sets_had_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "WebSearch")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is True

    def test_web_fetch_sets_had_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "WebFetch")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is True

    def test_read_does_not_set_had_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Read")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is False

    def test_bash_does_not_set_had_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Bash", command="ls -la")
        assert self.read_state(tmp_path, "sess-1")["had_work"] is False

    def test_kd_tk_log_sets_did_log(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Bash", command='kd tk log d4fc "did stuff"')
        assert self.read_state(tmp_path, "sess-1")["did_log"] is True

    def test_kd_ticket_log_sets_did_log(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Bash", command='kd ticket log d4fc "did stuff"')
        assert self.read_state(tmp_path, "sess-1")["did_log"] is True

    def test_unrelated_bash_does_not_set_did_log(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Bash", command="pytest")
        assert self.read_state(tmp_path, "sess-1")["did_log"] is False

    # --- Stop blocker ---

    def test_stop_blocks_when_had_work_no_log(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, kd_ticket_id="0042")
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "kd tk log 0042" in output["reason"]

    def test_stop_allows_when_did_log(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        self.tool_use(tmp_path, "Bash", command='kd tk log d4fc "summary"')
        result = self.stop(tmp_path)
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_stop_allows_when_no_work(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        result = self.stop(tmp_path)
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_stop_allows_when_stop_hook_active(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, stop_active=True)
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_bypass_skips_blocking(self, tmp_path: Path) -> None:
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, bypass=True)
        assert result.returncode == 0
        assert result.stdout == ""

    def test_missing_state_file_fails_open(self, tmp_path: Path) -> None:
        # No submit → no state file → Stop should not block.
        result = self.stop(tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "" or "block" not in result.stdout

    # --- Active ticket gating ---

    def test_stop_no_active_ticket_passes_through(self, tmp_path: Path) -> None:
        """No active ticket + had work => no block."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, kd_ticket_id="")
        assert result.returncode == 0
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_stop_active_ticket_blocks_with_real_id(self, tmp_path: Path) -> None:
        """Active ticket + had work + no log => block with concrete ticket ID."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        result = self.stop(tmp_path, kd_ticket_id="a1b2")
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "kd tk log a1b2" in output["reason"]
        # No placeholder tokens like <ticket-id>.
        assert "<" not in output["reason"]

    def test_stop_kd_current_failure_fails_open(self, tmp_path: Path) -> None:
        """If kd tk current --id fails or times out, Stop fails open."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        # Mock kd that exits 1 (no active ticket).
        result = self.stop(tmp_path, kd_ticket_id="")
        assert result.returncode == 0
        assert result.stdout.strip() == "" or "block" not in result.stdout

    def test_mid_turn_ticket_accept_enforces_at_stop(self, tmp_path: Path) -> None:
        """Ticket created/accepted mid-turn => Stop resolves current ticket at Stop time."""
        self.submit(tmp_path)
        self.tool_use(tmp_path, "Edit")
        # Simulate: at stop time, kd tk current --id now returns a ticket.
        result = self.stop(tmp_path, kd_ticket_id="0240")
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "kd tk log 0240" in output["reason"]

    # --- Multi-agent isolation ---

    def test_separate_sessions_no_cross_blocking(self, tmp_path: Path) -> None:
        # Session A does work, session B does not.
        self.submit(tmp_path, session_id="sess-a")
        self.submit(tmp_path, session_id="sess-b")
        self.tool_use(tmp_path, "Edit", session_id="sess-a")
        # Session B's Stop should not block.
        result = self.stop(tmp_path, session_id="sess-b")
        assert result.stdout.strip() == "" or "block" not in result.stdout
        # Session A's Stop should block.
        result = self.stop(tmp_path, session_id="sess-a", kd_ticket_id="0099")
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_sessions_have_independent_state(self, tmp_path: Path) -> None:
        self.submit(tmp_path, session_id="sess-a")
        self.submit(tmp_path, session_id="sess-b")
        self.tool_use(tmp_path, "Write", session_id="sess-a")
        self.tool_use(tmp_path, "Bash", session_id="sess-b", command='kd tk log x "y"')
        assert self.read_state(tmp_path, "sess-a") == {"had_work": True, "did_log": False}
        assert self.read_state(tmp_path, "sess-b") == {"had_work": False, "did_log": True}

    def test_stale_state_does_not_block_new_session(self, tmp_path: Path) -> None:
        # Create a state file for an old session that looks like it had work.
        runtime = tmp_path / ".kd" / "runtime"
        runtime.mkdir(parents=True)
        stale = runtime / "turn-old-session.json"
        stale.write_text(json.dumps({"had_work": True, "did_log": False}))
        # New session should not be affected.
        self.submit(tmp_path, session_id="new-session")
        result = self.stop(tmp_path, session_id="new-session")
        assert result.stdout.strip() == "" or "block" not in result.stdout
