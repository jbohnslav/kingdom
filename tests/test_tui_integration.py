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
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

from kingdom.agent import AgentConfig
from kingdom.council import Council
from kingdom.council.base import AgentResponse
from kingdom.thread import add_message, create_thread, list_messages, thread_dir
from kingdom.tui.app import ChatApp, InputArea, MessageLog
from kingdom.tui.poll import StreamDelta, StreamFinished, StreamStarted, ThinkingDelta
from kingdom.tui.widgets import ErrorPanel, MessagePanel, StreamingPanel, ThinkingPanel, WaitingPanel

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
    writable: bool = False
    agent_prompt: str = ""
    phase_prompt: str = ""
    prompts: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.config.name

    def query(
        self, prompt: str, timeout: int = 600, stream_path: Path | None = None, max_retries: int = 0
    ) -> AgentResponse:
        import time

        self.prompts.append(prompt)
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

    async def test_markdown_is_rendered(self, project, thread_id, fake_council) -> None:
        """Message bodies with markdown should use Textual's native Markdown widget."""
        from textual.widgets import Markdown as TextualMarkdown

        add_message(project, BRANCH, thread_id, from_="claude", to="king", body="This is **bold** and `code`")

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                log = app.query_one("#message-log", MessageLog)
                panels = log.query(MessagePanel)
                assert len(panels) == 1

                # MessagePanel should contain a Textual Markdown child widget
                md_children = panels[0].query(TextualMarkdown)
                assert len(md_children) == 1

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

    async def test_follow_ups_queue_behind_active_exchange(self, project, thread_id) -> None:
        council = make_fake_council(["claude", "codex"], delay=0.15)
        app = make_app(project, thread_id)

        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                input_area = app.query_one("#input-area", InputArea)
                input_area.insert("First question")
                await pilot.press("enter")

                await wait_until(pilot, lambda: all(member.prompts for member in council.members))

                input_area.insert("Queued follow-up")
                await pilot.press("enter")

                input_area.insert("Final follow-up")
                await pilot.press("enter")

                await wait_until(
                    pilot,
                    lambda: len(list_messages(project, BRANCH, thread_id)) == 9,
                    timeout=5.0,
                )
                await pilot.pause(delay=0.2)

                log = app.query_one("#message-log", MessageLog)
                king_panels = [panel for panel in log.query(MessagePanel) if panel.sender == "king"]
                assert [panel.body for panel in king_panels] == [
                    "First question",
                    "Queued follow-up",
                    "Final follow-up",
                ]

        messages = list_messages(project, BRANCH, thread_id)
        assert messages[0].body == "First question"
        assert messages[3].body == "Queued follow-up"
        assert messages[6].body == "Final follow-up"

        for offset in (0, 3, 6):
            assert messages[offset].from_ == "king"
            assert {message.from_ for message in messages[offset + 1 : offset + 3]} == {"claude", "codex"}

        for member in council.members:
            assert len(member.prompts) == 3
            assert "First question" in member.prompts[0]
            assert "Queued follow-up" not in member.prompts[0]
            assert "Final follow-up" not in member.prompts[0]
            assert "Queued follow-up" in member.prompts[1]
            assert "Final follow-up" not in member.prompts[1]
            assert "Final follow-up" in member.prompts[2]

    async def test_pending_follow_ups_resume_after_restart(self, project, thread_id) -> None:
        first_app = make_app(project, thread_id)
        first_council = make_fake_council(["claude", "codex"])
        pending_path = thread_dir(project, BRANCH, thread_id) / ".pending-messages.json"

        with patch.object(Council, "create", return_value=first_council):
            async with first_app.run_test(size=(120, 40)) as pilot:
                first_app.delivery_active = True
                input_area = first_app.query_one("#input-area", InputArea)
                input_area.insert("Queued before restart")
                await pilot.press("enter")
                input_area.insert("Second after restart")
                await pilot.press("enter")
                await pilot.pause()

                pending = json.loads(pending_path.read_text(encoding="utf-8"))
                assert [item["body"] for item in pending["deliveries"]] == [
                    "Queued before restart",
                    "Second after restart",
                ]

        resumed_council = make_fake_council(["claude", "codex"])
        resumed_app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=resumed_council):
            async with resumed_app.run_test(size=(120, 40)) as pilot:
                await wait_until(
                    pilot,
                    lambda: len(list_messages(project, BRANCH, thread_id)) == 6,
                    timeout=5.0,
                )
                await pilot.pause(delay=0.2)

                log = resumed_app.query_one("#message-log", MessageLog)
                king_panels = [panel for panel in log.query(MessagePanel) if panel.sender == "king"]
                assert [panel.body for panel in king_panels] == [
                    "Queued before restart",
                    "Second after restart",
                ]

        messages = list_messages(project, BRANCH, thread_id)
        assert [messages[0].body, messages[3].body] == ["Queued before restart", "Second after restart"]
        assert not pending_path.exists()
        for member in resumed_council.members:
            assert len(member.prompts) == 2
            assert "Second after restart" not in member.prompts[0]
            assert "Second after restart" in member.prompts[1]

    async def test_restart_reconciles_already_persisted_pending_message(self, project, thread_id) -> None:
        first_app = make_app(project, thread_id)
        first_council = make_fake_council(["claude", "codex"])
        pending_path = thread_dir(project, BRANCH, thread_id) / ".pending-messages.json"

        with patch.object(Council, "create", return_value=first_council):
            async with first_app.run_test(size=(120, 40)) as pilot:
                first_app.delivery_active = True
                input_area = first_app.query_one("#input-area", InputArea)
                input_area.insert("Persisted before crash")
                await pilot.press("enter")
                await pilot.pause()

        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        delivery_id = pending["deliveries"][0]["id"]
        add_message(
            project,
            BRANCH,
            thread_id,
            from_="king",
            to="all",
            body="Persisted before crash",
            delivery_id=delivery_id,
        )

        resumed_council = make_fake_council(["claude", "codex"])
        resumed_app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=resumed_council):
            async with resumed_app.run_test(size=(120, 40)) as pilot:
                await wait_until(
                    pilot,
                    lambda: len(list_messages(project, BRANCH, thread_id)) == 3,
                    timeout=5.0,
                )

                messages = list_messages(project, BRANCH, thread_id)
                assert len(messages) == 3
                assert messages[0].delivery_id == delivery_id
                assert all(len(member.prompts) == 1 for member in resumed_council.members)
                assert not pending_path.exists()


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

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=council):
            async with app.run_test(size=(120, 40)) as pilot:
                app.chat_mode = "round_robin"
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

                # Wait for all messages: king + 2 broadcast + 2 auto-turn = 5 new files
                await wait_until(
                    pilot,
                    lambda: len(list(tdir.glob("[0-9]*-*.md"))) >= len(msgs_before) + 5,
                    timeout=5.0,
                )

                app.poll_updates()
                await pilot.pause(delay=0.2)

                # New non-king messages: 2 broadcast + 2 auto-turn = 4
                new_msgs = sorted(set(tdir.glob("[0-9]*-*.md")) - msgs_before)
                member_msgs = [p for p in new_msgs if "king" not in p.name]
                assert len(member_msgs) == 4

                # First 2 are broadcast (parallel, order may vary), last 2 are auto-turn (round-robin)
                auto_turn_msgs = member_msgs[2:]
                assert "claude" in auto_turn_msgs[0].name
                assert "codex" in auto_turn_msgs[1].name


# ---------------------------------------------------------------------------
# Scenario 12: Interrupted partial messages labeled on history replay
# ---------------------------------------------------------------------------


class TestInterruptedLabel:
    async def test_interrupted_partial_labeled_in_history(self, project, thread_id, fake_council) -> None:
        """Interrupted messages with partial text should show the interrupted marker on replay."""
        # Pre-populate a normal message and an interrupted message
        add_message(project, BRANCH, thread_id, from_="king", to="all", body="Ask something")
        add_message(project, BRANCH, thread_id, from_="claude", to="king", body="Normal complete response")
        add_message(
            project,
            BRANCH,
            thread_id,
            from_="codex",
            to="king",
            body="Partial answer\n\n*[Interrupted — response may be incomplete]*",
        )

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                log = app.query_one("#message-log", MessageLog)

                # Normal response renders as MessagePanel
                panels = log.query(MessagePanel)
                normal = [p for p in panels if p.sender == "claude"]
                assert len(normal) == 1

                # Interrupted response should render as ErrorPanel (not MessagePanel)
                error_panels = log.query(ErrorPanel)
                interrupted = [p for p in error_panels if p.sender == "codex"]
                assert len(interrupted) == 1

    async def test_normal_response_not_labeled(self, project, thread_id, fake_council) -> None:
        """Normal completed responses should not contain interrupted markers."""
        add_message(project, BRANCH, thread_id, from_="claude", to="king", body="Complete response")

        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)):
                log = app.query_one("#message-log", MessageLog)
                panels = log.query(MessagePanel)
                assert len(panels) == 1
                assert panels[0].sender == "claude"
                # No error panels
                assert len(log.query(ErrorPanel)) == 0


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


# ---------------------------------------------------------------------------
# Scenario 13: StreamingPanel lifecycle (cca0)
# ---------------------------------------------------------------------------


class TestStreamingPanelLifecycle:
    """Verify intermediate streaming state: StreamingPanel appears, updates, and
    gets replaced by MessagePanel when the response finalizes."""

    async def test_streaming_panel_appears_on_stream_started(self, project, thread_id, fake_council) -> None:
        """StreamingPanel is mounted when a StreamStarted event fires."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)
                # Mount a WaitingPanel first (simulating post-send state)
                log.mount(WaitingPanel(sender="claude", id="wait-claude"))
                await pilot.pause(delay=0.1)

                # Fire StreamStarted via handler
                app.handle_stream_started(log, StreamStarted(member="claude"))
                await pilot.pause(delay=0.1)

                # StreamingPanel should exist, WaitingPanel should be gone
                assert len(log.query(StreamingPanel)) == 1
                assert log.query_one(StreamingPanel).sender == "claude"
                assert len(log.query(WaitingPanel)) == 0

    async def test_streaming_panel_content_updates(self, project, thread_id, fake_council) -> None:
        """StreamingPanel content updates as StreamDelta events arrive."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)

                # Start streaming
                app.handle_stream_started(log, StreamStarted(member="claude"))
                await pilot.pause(delay=0.1)

                # First delta
                app.handle_stream_delta(log, StreamDelta(member="claude", full_text="Hello"))
                await pilot.pause(delay=0.1)
                panel = log.query_one(StreamingPanel)
                assert panel.content_text == "Hello"

                # Second delta (accumulated)
                app.handle_stream_delta(log, StreamDelta(member="claude", full_text="Hello world"))
                await pilot.pause(delay=0.2)
                assert panel.content_text == "Hello world"

                # Verify content is rendered through a Textual Markdown widget
                from textual.widgets import Markdown as TextualMarkdown

                md = panel.query_one(TextualMarkdown)
                assert md is not None

    async def test_streaming_panel_replaced_by_message(self, project, thread_id, fake_council) -> None:
        """StreamingPanel is removed when stream finishes and MessagePanel takes its place."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)

                # Simulate streaming lifecycle
                app.handle_stream_started(log, StreamStarted(member="claude"))
                app.handle_stream_delta(log, StreamDelta(member="claude", full_text="Final answer"))
                await pilot.pause(delay=0.1)
                assert len(log.query(StreamingPanel)) == 1

                # Stream finishes
                app.handle_stream_finished(StreamFinished(member="claude"))
                await pilot.pause(delay=0.1)

                # StreamingPanel should be gone
                assert len(log.query(StreamingPanel)) == 0

    async def test_multiple_members_stream_concurrently(self, project, thread_id, fake_council) -> None:
        """Each member gets its own StreamingPanel during concurrent streaming."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)

                # Both members start streaming
                app.handle_stream_started(log, StreamStarted(member="claude"))
                app.handle_stream_started(log, StreamStarted(member="codex"))
                await pilot.pause(delay=0.1)

                panels = log.query(StreamingPanel)
                assert len(panels) == 2
                senders = {p.sender for p in panels}
                assert senders == {"claude", "codex"}

                # Update each independently
                app.handle_stream_delta(log, StreamDelta(member="claude", full_text="Claude says"))
                app.handle_stream_delta(log, StreamDelta(member="codex", full_text="Codex says"))
                await pilot.pause(delay=0.1)

                for panel in log.query(StreamingPanel):
                    if panel.sender == "claude":
                        assert panel.content_text == "Claude says"
                    else:
                        assert panel.content_text == "Codex says"


# ---------------------------------------------------------------------------
# Scenario 14: ThinkingPanel lifecycle (5e30)
# ---------------------------------------------------------------------------


class TestThinkingPanelLifecycle:
    """Verify ThinkingPanel auto-collapse, hide mode, show mode, and state persistence."""

    async def test_thinking_panel_auto_collapses_on_answer(self, project, thread_id, fake_council) -> None:
        """In auto mode, ThinkingPanel collapses when first StreamDelta arrives."""
        app = make_app(project, thread_id)
        app.thinking_visibility = "auto"
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)

                # Thinking starts
                app.handle_thinking_delta(log, ThinkingDelta(member="claude", full_text="Let me think..."))
                await pilot.pause(delay=0.1)

                panel = log.query_one(ThinkingPanel)
                assert panel.expanded is True
                assert panel.thinking_text == "Let me think..."

                # First answer token triggers auto-collapse
                app.handle_stream_started(log, StreamStarted(member="claude"))
                app.handle_stream_delta(log, StreamDelta(member="claude", full_text="Answer"))
                await pilot.pause(delay=0.1)

                assert panel.expanded is False
                assert panel.has_class("collapsed")

    async def test_thinking_panel_never_mounted_in_hide_mode(self, project, thread_id, fake_council) -> None:
        """In hide mode, ThinkingDelta events are ignored — no ThinkingPanel mounted."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                # Set after mount (on_mount loads from config, which defaults to "auto")
                app.thinking_visibility = "hide"
                log = app.query_one("#message-log", MessageLog)

                app.handle_thinking_delta(log, ThinkingDelta(member="claude", full_text="Thinking..."))
                await pilot.pause(delay=0.1)

                assert len(log.query(ThinkingPanel)) == 0

    async def test_thinking_panel_stays_expanded_in_show_mode(self, project, thread_id, fake_council) -> None:
        """In show mode, ThinkingPanel stays expanded even after answer tokens arrive."""
        app = make_app(project, thread_id)
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                app.thinking_visibility = "show"
                log = app.query_one("#message-log", MessageLog)

                # Thinking starts
                app.handle_thinking_delta(log, ThinkingDelta(member="claude", full_text="Deep thoughts"))
                await pilot.pause(delay=0.1)

                panel = log.query_one(ThinkingPanel)
                assert panel.expanded is True

                # Answer arrives — in show mode, auto-collapse is skipped
                app.handle_stream_started(log, StreamStarted(member="claude"))
                app.handle_stream_delta(log, StreamDelta(member="claude", full_text="Response"))
                await pilot.pause(delay=0.1)

                # Panel should still be expanded (show mode doesn't auto-collapse)
                assert panel.expanded is True
                assert not panel.has_class("collapsed")

    async def test_ctrl_t_cycles_thinking_modes(self, project, thread_id, fake_council) -> None:
        """Ctrl+T cycles through auto -> show -> hide -> auto."""
        app = make_app(project, thread_id)
        app.thinking_visibility = "auto"
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                assert app.thinking_visibility == "auto"

                await pilot.press("ctrl+t")
                await pilot.pause(delay=0.1)
                assert app.thinking_visibility == "show"

                await pilot.press("ctrl+t")
                await pilot.pause(delay=0.1)
                assert app.thinking_visibility == "hide"

                await pilot.press("ctrl+t")
                await pilot.pause(delay=0.1)
                assert app.thinking_visibility == "auto"

    async def test_thinking_panel_persists_when_new_message_arrives(self, project, thread_id, fake_council) -> None:
        """ThinkingPanel gets a sequence-specific ID when its member's response finalizes,
        so it persists in the log rather than being removed."""
        app = make_app(project, thread_id)
        app.thinking_visibility = "auto"
        with patch.object(Council, "create", return_value=fake_council):
            async with app.run_test(size=(120, 40)) as pilot:
                log = app.query_one("#message-log", MessageLog)

                # Mount thinking panel
                app.handle_thinking_delta(log, ThinkingDelta(member="claude", full_text="Reasoning..."))
                await pilot.pause(delay=0.1)
                assert len(log.query(ThinkingPanel)) == 1

                # Simulate finalized message arriving via poller
                from kingdom.tui.poll import NewMessage

                app.handle_new_message(log, NewMessage(sequence=1, sender="claude", body="Final answer"))
                await pilot.pause(delay=0.1)

                # ThinkingPanel should still exist (with a new sequence-specific ID)
                thinking_panels = log.query(ThinkingPanel)
                assert len(thinking_panels) == 1
                assert "thinking-claude-1" in thinking_panels[0].id

                # And it should be auto-collapsed
                assert thinking_panels[0].expanded is False
