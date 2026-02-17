"""Textual integration tests for kd chat — drives real UI via app.run_test() + Pilot.

Gated behind --run-textual-integration flag (see conftest.py).

Run commands:
    pytest                                    # fast — skips integration tests
    pytest --run-textual-integration          # full — includes integration tests (~4s extra)
    pytest --run-textual-integration -m textual_integration  # integration tests only
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from kingdom.agent import AgentConfig
from kingdom.council import Council
from kingdom.council.base import AgentResponse
from kingdom.state import ensure_branch_layout
from kingdom.thread import add_message, create_thread, thread_dir
from kingdom.tui.app import ChatApp, InputArea, MessageLog
from kingdom.tui.widgets import ErrorPanel, MessagePanel, WaitingPanel

pytestmark = pytest.mark.textual_integration

BRANCH = "test/integration"
MEMBERS = ["king", "claude", "codex"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def wait_until(pilot, predicate, *, timeout: float = 2.0, interval: float = 0.05):
    """Poll *predicate* until it returns True or *timeout* expires.

    Calls ``pilot.pause()`` between attempts so Textual processes events.
    """
    elapsed = 0.0
    while elapsed < timeout:
        await pilot.pause(delay=interval)
        if predicate():
            return
        elapsed += interval
    raise TimeoutError(f"Predicate not satisfied after {timeout}s")


def make_agent_config(name: str) -> AgentConfig:
    return AgentConfig(name=name, backend="claude_code", cli="echo", resume_flag="--resume")


@dataclass
class FakeMember:
    """Lightweight stand-in for CouncilMember used in integration tests.

    The ``query`` method writes a canned response file to the thread dir
    (simulating what the real agent subprocess does) and returns an
    AgentResponse. No subprocess is spawned.
    """

    config: AgentConfig
    response_text: str = "Hello from {name}"
    response_error: str | None = None
    delay: float = 0.0
    session_id: str | None = None
    process: object = None  # mimics CouncilMember.process
    preamble: str = ""
    base: Path | None = None
    branch: str | None = None
    agent_prompt: str = ""
    phase_prompt: str = ""

    @property
    def name(self) -> str:
        return self.config.name

    def query(
        self, prompt: str, timeout: int = 600, stream_path: Path | None = None, max_retries: int = 0
    ) -> AgentResponse:
        import time

        if self.delay:
            time.sleep(self.delay)

        text = self.response_text.format(name=self.name)

        # Write stream events so the poller picks them up
        if stream_path:
            stream_path.parent.mkdir(parents=True, exist_ok=True)
            with open(stream_path, "w", encoding="utf-8") as f:
                # Write a single Claude-style stream event
                event = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                }
                f.write(json.dumps(event) + "\n")

        return AgentResponse(
            name=self.name,
            text=text,
            error=self.response_error,
            elapsed=self.delay,
            raw=text,
        )

    def reset_session(self) -> None:
        self.session_id = None


def make_fake_council(member_names: list[str], **member_kwargs) -> Council:
    """Build a Council with FakeMember instances."""
    members = []
    for name in member_names:
        cfg = make_agent_config(name)
        members.append(FakeMember(config=cfg, **member_kwargs))
    return Council(members=members, timeout=10, auto_messages=-1, mode="broadcast")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    return tmp_path


@pytest.fixture()
def thread_id(project: Path) -> str:
    """Create a council thread with claude + codex members."""
    tid = "council-inttest"
    create_thread(project, BRANCH, tid, MEMBERS, "council")
    return tid


@pytest.fixture()
def fake_council() -> Council:
    """Council with FakeMembers (claude, codex) that return canned text."""
    return make_fake_council(["claude", "codex"])


def make_app(project: Path, thread_id: str) -> ChatApp:
    """Build a ChatApp pointed at the test project."""
    return ChatApp(base=project, branch=BRANCH, thread_id=thread_id)


# ---------------------------------------------------------------------------
# Scenario 1: App boot — header, input focus, history render
# ---------------------------------------------------------------------------


class TestAppBoot:
    async def test_header_shows_thread_info(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                header = app.query_one("#header-bar")
                text = str(header.content)
                assert thread_id in text
                assert "claude" in text
                assert "codex" in text

    async def test_input_area_has_focus(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                input_area = app.query_one("#input-area", InputArea)
                assert input_area.has_focus

    async def test_existing_history_renders(self, project, thread_id, fake_council) -> None:
        # Pre-populate some messages
        add_message(project, BRANCH, thread_id, from_="king", to="all", body="Hello council")
        add_message(project, BRANCH, thread_id, from_="claude", to="king", body="Hi from Claude")
        add_message(project, BRANCH, thread_id, from_="codex", to="king", body="Hi from Codex")

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                log = app.query_one("#message-log", MessageLog)
                panels = log.query(MessagePanel)
                assert len(panels) == 3
                # First message is from king
                assert panels[0].sender == "king"
                assert panels[1].sender == "claude"
                assert panels[2].sender == "codex"

    async def test_no_history_starts_clean(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                log = app.query_one("#message-log", MessageLog)
                panels = log.query(MessagePanel)
                assert len(panels) == 0


# ---------------------------------------------------------------------------
# Scenario 2: Keyboard — Enter sends, Shift+Enter inserts newline
# ---------------------------------------------------------------------------


class TestKeyboard:
    async def test_enter_sends_message(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                # Type a message
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Hello world")
                await pilot.pause()

                # Press Enter
                await pilot.press("enter")
                await pilot.pause(delay=0.1)

                # Input should be cleared
                assert input_area.text == ""

                # King message should appear in the log
                log = app.query_one("#message-log", MessageLog)
                king_panels = [p for p in log.query(MessagePanel) if p.sender == "king"]
                assert len(king_panels) == 1
                assert "Hello world" in king_panels[0].body

    async def test_shift_enter_does_not_send(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("line1")
                await pilot.press("shift+enter")
                await pilot.pause()

                # Text should NOT have been sent (input not cleared)
                assert "line1" in input_area.text

                # No king message in log
                log = app.query_one("#message-log", MessageLog)
                king_panels = [p for p in log.query(MessagePanel) if p.sender == "king"]
                assert len(king_panels) == 0


# ---------------------------------------------------------------------------
# Scenario 3: Send lifecycle — king message + waiting panels
# ---------------------------------------------------------------------------


class TestSendLifecycle:
    async def test_king_message_appears_immediately(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        # Patch run_query to be a no-op so we can inspect the immediate UI state
        with (
            patch.object(Council, "create", return_value=fake_council),
            patch.object(ChatApp, "run_query", new_callable=lambda: lambda *a, **kw: asyncio.sleep(999)),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Test message")
                await pilot.press("enter")
                await wait_until(pilot, lambda: len(app.query_one("#message-log", MessageLog).query(MessagePanel)) > 0)

                log = app.query_one("#message-log", MessageLog)
                king_panels = [p for p in log.query(MessagePanel) if p.sender == "king"]
                assert len(king_panels) == 1
                assert "Test message" in king_panels[0].body

    async def test_waiting_panels_mount_for_targets(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with (
            patch.object(Council, "create", return_value=fake_council),
            patch.object(ChatApp, "run_query", new_callable=lambda: lambda *a, **kw: asyncio.sleep(999)),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Test broadcast")
                await pilot.press("enter")
                await wait_until(pilot, lambda: len(app.query_one("#message-log", MessageLog).query(WaitingPanel)) >= 2)

                log = app.query_one("#message-log", MessageLog)
                waiting = log.query(WaitingPanel)
                waiting_names = {w.sender for w in waiting}
                assert "claude" in waiting_names
                assert "codex" in waiting_names

    async def test_directed_message_targets_single_member(self, project, thread_id, fake_council) -> None:
        """@member directed message only queries that member, not broadcast."""
        app = make_app(project, thread_id)
        with (
            patch.object(Council, "create", return_value=fake_council),
            patch.object(ChatApp, "run_query", new_callable=lambda: lambda *a, **kw: asyncio.sleep(999)),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("@claude What do you think?")
                await pilot.press("enter")
                await wait_until(pilot, lambda: len(app.query_one("#message-log", MessageLog).query(WaitingPanel)) >= 1)

                log = app.query_one("#message-log", MessageLog)
                waiting = log.query(WaitingPanel)
                waiting_names = {w.sender for w in waiting}
                # Only claude should be queried, not codex
                assert "claude" in waiting_names
                assert "codex" not in waiting_names


# ---------------------------------------------------------------------------
# Scenario 4: Stream lifecycle — waiting → streaming → finalized
# ---------------------------------------------------------------------------


class TestStreamLifecycle:
    async def test_stream_to_finalized(self, project, thread_id, fake_council) -> None:
        """Full cycle: send message → query completes → poll renders finalized panels with correct content."""
        app = make_app(project, thread_id)

        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                tdir = thread_dir(project, BRANCH, thread_id)

                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Please respond")
                await pilot.press("enter")

                # Wait for both member responses to be persisted
                await wait_until(
                    pilot,
                    lambda: len(list(tdir.glob("*-claude.md"))) >= 1 and len(list(tdir.glob("*-codex.md"))) >= 1,
                    timeout=5.0,
                )

                # Pump the poller to process all events
                app.poll_updates()
                await pilot.pause(delay=0.2)

                log = app.query_one("#message-log", MessageLog)

                # Should have finalized message panels for both members (not waiting)
                msg_panels = [p for p in log.query(MessagePanel) if p.sender != "king"]
                senders = {p.sender for p in msg_panels}
                assert "claude" in senders
                assert "codex" in senders

                # Verify response content matches FakeMember output
                for panel in msg_panels:
                    assert f"Hello from {panel.sender}" in panel.body

                # No waiting or streaming panels should remain
                assert len(log.query(WaitingPanel)) == 0


# ---------------------------------------------------------------------------
# Scenario 5: Error lifecycle — ErrorPanel renders
# ---------------------------------------------------------------------------


class TestErrorLifecycle:
    async def test_error_response_renders_error_panel(self, project, thread_id) -> None:
        """An agent that returns an error should produce an ErrorPanel with timeout labeling."""
        error_council = make_fake_council(["claude", "codex"], response_text="", response_error="Timeout after 10s")

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=error_council):
            async with app.run_test(size=(120, 40)) as pilot:
                tdir = thread_dir(project, BRANCH, thread_id)

                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Error test")
                await pilot.press("enter")

                # Wait for error messages to be written
                await wait_until(
                    pilot,
                    lambda: len(list(tdir.glob("*-claude.md"))) >= 1,
                    timeout=5.0,
                )

                app.poll_updates()
                await pilot.pause(delay=0.2)

                log = app.query_one("#message-log", MessageLog)
                error_panels = log.query(ErrorPanel)
                assert len(error_panels) >= 1

                # Verify timeout-specific labeling
                for panel in error_panels:
                    assert panel.timed_out is True
                    assert "Timeout" in panel.error


# ---------------------------------------------------------------------------
# Scenario 6: External updates — files written while app runs
# ---------------------------------------------------------------------------


class TestExternalUpdates:
    async def test_external_message_appears(self, project, thread_id, fake_council) -> None:
        """Messages written by an external process show up via polling."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                # Wait for app to fully mount
                await pilot.pause(delay=0.2)

                # External process writes a message
                add_message(project, BRANCH, thread_id, from_="king", to="all", body="External msg")

                # Poll to pick it up
                app.poll_updates()
                await pilot.pause(delay=0.2)

                log = app.query_one("#message-log", MessageLog)
                panels = log.query(MessagePanel)
                bodies = [p.body for p in panels]
                assert any("External msg" in b for b in bodies)


# ---------------------------------------------------------------------------
# Scenario 7: Slash commands
# ---------------------------------------------------------------------------


class TestSlashCommands:
    async def test_help_shows_system_message(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("/help")
                await pilot.press("enter")
                await pilot.pause(delay=0.1)

                log = app.query_one("#message-log", MessageLog)
                system_msgs = log.query(".system-message")
                assert len(system_msgs) >= 1
                text = str(system_msgs[0].content)
                assert "/mute" in text
                assert "/quit" in text

    async def test_mute_excludes_member(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)

                # Mute claude
                input_area.insert("/mute claude")
                await pilot.press("enter")
                await wait_until(pilot, lambda: "claude" in app.muted)

                # Check system message confirms mute
                log = app.query_one("#message-log", MessageLog)
                system_msgs = log.query(".system-message")
                assert len(system_msgs) >= 1
                assert "Muted claude" in str(system_msgs[0].content)

    async def test_unmute_reinclude_member(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)

                # Mute then unmute
                input_area.insert("/mute claude")
                await pilot.press("enter")
                await wait_until(pilot, lambda: "claude" in app.muted)

                input_area.insert("/unmute claude")
                await pilot.press("enter")
                await wait_until(pilot, lambda: "claude" not in app.muted)

    async def test_unknown_command(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("/foobar")
                await pilot.press("enter")
                await pilot.pause(delay=0.1)

                log = app.query_one("#message-log", MessageLog)
                system_msgs = log.query(".system-message")
                assert len(system_msgs) >= 1
                assert "Unknown command" in str(system_msgs[0].content)

    async def test_quit_exits(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("/quit")
                await pilot.press("enter")
                # App should exit — the context manager handles this


# ---------------------------------------------------------------------------
# Scenario 8: Escape interrupt
# ---------------------------------------------------------------------------


class TestEscapeInterrupt:
    async def test_escape_with_no_active_queries_exits(self, project, thread_id, fake_council) -> None:
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                # No active queries — Escape should exit
                await pilot.press("escape")
                # App exits — no assertion needed, just shouldn't hang

    async def test_escape_interrupts_active_query(self, project, thread_id) -> None:
        """First Escape terminates active processes and replaces WaitingPanels with ErrorPanels."""
        import subprocess
        from unittest.mock import MagicMock

        council = make_fake_council(["claude", "codex"])
        # Simulate active processes
        for member in council.members:
            member.process = MagicMock(spec=subprocess.Popen)

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                # Mount waiting panels to simulate in-flight queries
                log = app.query_one("#message-log", MessageLog)
                log.mount(WaitingPanel(sender="claude", id="wait-claude"))
                log.mount(WaitingPanel(sender="codex", id="wait-codex"))
                await pilot.pause(delay=0.1)

                # First Escape — should interrupt, not exit
                await pilot.press("escape")
                await pilot.pause(delay=0.1)

                assert app.interrupted is True
                # Processes should have been terminated
                for member in council.members:
                    member.process.terminate.assert_called_once()

                # WaitingPanels should be replaced with ErrorPanels showing "Interrupted"
                error_panels = log.query(ErrorPanel)
                assert len(error_panels) == 2
                interrupted_names = {p.sender for p in error_panels}
                assert interrupted_names == {"claude", "codex"}
                for panel in error_panels:
                    assert "Interrupted" in panel.error

                # No waiting panels should remain
                assert len(log.query(WaitingPanel)) == 0

    async def test_second_escape_exits(self, project, thread_id) -> None:
        """Second Escape after interrupt should exit the app."""
        import subprocess
        from unittest.mock import MagicMock

        council = make_fake_council(["claude", "codex"])
        for member in council.members:
            member.process = MagicMock(spec=subprocess.Popen)

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)
                log.mount(WaitingPanel(sender="claude", id="wait-claude"))
                await pilot.pause(delay=0.1)

                # First Escape — interrupt
                await pilot.press("escape")
                await pilot.pause(delay=0.1)

                # Clear processes (simulating terminated)
                for member in council.members:
                    member.process = None

                # Second Escape — exit
                await pilot.press("escape")
                # App exits


# ---------------------------------------------------------------------------
# Scenario 9: Auto-turn follow-up
# ---------------------------------------------------------------------------


class TestAutoTurn:
    async def test_follow_up_sequential_round_robin(self, project, thread_id) -> None:
        """After first exchange, follow-up queries proceed sequentially with correct budget and order."""
        council = make_fake_council(["claude", "codex"])
        council.auto_messages = 2  # exactly 2 follow-up messages

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                tdir = thread_dir(project, BRANCH, thread_id)

                # First exchange — seed king + member messages
                add_message(project, BRANCH, thread_id, from_="king", to="all", body="Initial question")
                add_message(project, BRANCH, thread_id, from_="claude", to="king", body="Claude initial")
                add_message(project, BRANCH, thread_id, from_="codex", to="king", body="Codex initial")

                # Reload history so poller knows about them
                app.load_history()
                await pilot.pause(delay=0.1)

                msgs_before = set(tdir.glob("[0-9]*-*.md"))

                # Now send a follow-up (not first exchange since prior responses exist)
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Follow up question")
                await pilot.press("enter")

                # Wait for auto-turn messages to be written (king + 2 auto-turn responses)
                await wait_until(
                    pilot,
                    lambda: len(list(tdir.glob("[0-9]*-*.md"))) >= len(msgs_before) + 3,
                    timeout=5.0,
                )

                app.poll_updates()
                await pilot.pause(delay=0.2)

                # Verify exactly 2 follow-up messages were written (respecting budget)
                new_msgs = sorted(set(tdir.glob("[0-9]*-*.md")) - msgs_before)
                auto_turn_msgs = [p for p in new_msgs if "king" not in p.name]
                assert len(auto_turn_msgs) == 2

                # Verify round-robin order: claude first, then codex
                assert "claude" in auto_turn_msgs[0].name
                assert "codex" in auto_turn_msgs[1].name


# ---------------------------------------------------------------------------
# Scenario 10: Fresh thread isolation
# ---------------------------------------------------------------------------


class TestThreadIsolation:
    async def test_session_ids_cleared_after_query(self, project, thread_id) -> None:
        """Chat mode clears session_id after each query to prevent context leakage."""
        council = make_fake_council(["claude", "codex"])
        # Pre-set session IDs (simulating prior session)
        for member in council.members:
            member.session_id = "old-session-123"

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Test isolation")
                await pilot.press("enter")

                tdir = thread_dir(project, BRANCH, thread_id)
                await wait_until(
                    pilot,
                    lambda: len(list(tdir.glob("*-claude.md"))) >= 1,
                    timeout=5.0,
                )

                # session_id should be cleared after query completes
                for member in council.members:
                    assert member.session_id is None


# ---------------------------------------------------------------------------
# Scenario 11: Speaker label sanitization
# ---------------------------------------------------------------------------


class TestSpeakerLabelSanitization:
    async def test_no_duplicated_speaker_prefix(self, project, thread_id) -> None:
        """Response bodies should not have duplicated speaker prefixes like 'codex: codex:'."""
        # Create a council with a member that echoes its own name prefix
        council = make_fake_council(["claude", "codex"])
        # Simulate agent echoing "claude: Hello" — thread_body() should strip "claude: "
        for member in council.members:
            member.response_text = f"{member.name}: Hello from {member.name}"

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("Test sanitization")
                await pilot.press("enter")

                tdir = thread_dir(project, BRANCH, thread_id)
                await wait_until(
                    pilot,
                    lambda: len(list(tdir.glob("*-claude.md"))) >= 1,
                    timeout=5.0,
                )

                # Read persisted messages — check for no doubled prefix
                for path in sorted(tdir.glob("[0-9]*-*.md")):
                    if "king" in path.name:
                        continue
                    content = path.read_text(encoding="utf-8")
                    # Should not contain "name: name:" pattern
                    for name in ["claude", "codex"]:
                        assert f"{name}: {name}:" not in content
