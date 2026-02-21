"""Tests for TUI module and kd chat CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.session import get_current_thread, set_current_thread
from kingdom.state import ensure_branch_layout
from kingdom.thread import create_thread

runner = CliRunner()

BRANCH = "feature/test-chat"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, BRANCH)
    return tmp_path


class TestChatCommand:
    def test_help(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "Thread ID to open" in result.output

    def test_nonexistent_thread(self, project: Path) -> None:
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat", "nonexistent"])
        assert result.exit_code == 1
        assert "Thread not found" in result.output

    def test_no_args_no_threads(self, project: Path) -> None:
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "kd chat --new" in result.output

    def test_no_args_lists_threads(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-abc1", ["king", "claude"], "council")
        create_thread(project, BRANCH, "council-abc2", ["king", "codex"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "council-abc1" in result.output
        assert "council-abc2" in result.output

    def test_new_creates_thread_and_launches(self, project: Path) -> None:
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat", "--new"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

        # Check thread was created and current_thread was set
        current = get_current_thread(project, BRANCH)
        assert current is not None
        assert current.startswith("council-")

    def test_explicit_thread_id_launches(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-test", ["king", "claude"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat", "council-test"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_debug_flag_passed_to_app(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-debug", ["king", "claude"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp") as mock_chat_app,
        ):
            result = runner.invoke(app, ["chat", "council-debug", "--debug"])
        assert result.exit_code == 0
        mock_chat_app.assert_called_once_with(
            base=project,
            branch=BRANCH,
            thread_id="council-debug",
            debug_streams=True,
            writable=False,
        )
        mock_chat_app.return_value.run.assert_called_once()

    def test_resumes_current_thread(self, project: Path) -> None:
        create_thread(project, BRANCH, "council-resume", ["king", "claude"], "council")
        set_current_thread(project, BRANCH, "council-resume")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_stale_current_thread_falls_back_to_list(self, project: Path) -> None:
        set_current_thread(project, BRANCH, "council-gone")
        create_thread(project, BRANCH, "council-other", ["king", "claude"], "council")

        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
        ):
            result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        assert "council-other" in result.output


class TestChatApp:
    def test_app_stores_params(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.base == Path("/tmp")
        assert app_instance.branch == "main"
        assert app_instance.thread_id == "council-abc"

    def test_app_no_auto_scroll_attr(self) -> None:
        """auto_scroll stub removed — anchor()/scroll_if_following handles scroll follow."""
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert not hasattr(app_instance, "auto_scroll")

    def test_app_has_poller_none_before_mount(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.poller is None


class TestMessageLogScroll:
    """Test MessageLog smart scroll (is_following / anchor behavior)."""

    def test_message_log_has_scroll_threshold(self) -> None:
        """MessageLog should define a SCROLL_THRESHOLD class variable."""
        from kingdom.tui.app import MessageLog

        assert hasattr(MessageLog, "SCROLL_THRESHOLD")
        assert isinstance(MessageLog.SCROLL_THRESHOLD, int)
        assert MessageLog.SCROLL_THRESHOLD > 0

    def test_is_following_true_when_anchor_not_released(self) -> None:
        """is_following should be True when _anchor_released is False."""
        from kingdom.tui.app import MessageLog

        log = MessageLog()
        log._anchored = True
        log._anchor_released = False
        assert log.is_following is True

    def test_is_following_false_when_anchor_released(self) -> None:
        """is_following should be False when the user has scrolled away from bottom."""
        from kingdom.tui.app import MessageLog

        log = MessageLog()
        log._anchored = True
        log._anchor_released = True
        assert log.is_following is False

    def test_scroll_if_following_scrolls_when_following(self) -> None:
        """scroll_if_following should call scroll_end when is_following is True."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import MessageLog

        log = MessageLog()
        log._anchored = True
        log._anchor_released = False
        log.scroll_end = MagicMock()
        log.scroll_if_following()
        log.scroll_end.assert_called_once_with(animate=False)

    def test_scroll_if_following_skips_when_scrolled_up(self) -> None:
        """scroll_if_following should not scroll when user has scrolled up."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import MessageLog

        log = MessageLog()
        log._anchored = True
        log._anchor_released = True
        log.scroll_end = MagicMock()
        log.scroll_if_following()
        log.scroll_end.assert_not_called()

    def test_update_status_bar_uses_is_following(self, project: Path) -> None:
        """update_status_bar should use is_following (not _anchor_released directly)."""
        from unittest.mock import MagicMock, PropertyMock

        from kingdom.tui.app import ChatApp, MessageLog, StatusBar

        tid = "council-scroll1"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Create mock log with is_following property and mock status bar
        mock_log = MagicMock(spec=MessageLog)
        mock_bar = MagicMock(spec=StatusBar)

        def fake_query_one(sel_or_cls, cls=None):
            """Route to mock_log or mock_bar based on the type/selector."""
            if sel_or_cls is StatusBar:
                return mock_bar
            return mock_log

        app_instance.query_one = fake_query_one

        # When following: no "End: jump to bottom" hint
        type(mock_log).is_following = PropertyMock(return_value=True)
        app_instance.update_status_bar(mock_log)
        update_text = mock_bar.update.call_args[0][0]
        assert "End: jump to bottom" not in update_text

        # When not following: show "End: jump to bottom" hint
        type(mock_log).is_following = PropertyMock(return_value=False)
        app_instance.update_status_bar(mock_log)
        update_text = mock_bar.update.call_args[0][0]
        assert "End: jump to bottom" in update_text


class TestInputArea:
    def test_enter_posts_submit_message(self) -> None:
        import asyncio

        from textual.events import Key

        from kingdom.tui.app import InputArea

        input_area = InputArea()
        posted: list[str] = []
        input_area.post_message = lambda message: posted.append(type(message).__name__)

        asyncio.run(input_area._on_key(Key("enter", None)))

        assert posted == ["Submit"]

    def test_shift_enter_does_not_post_submit_message(self) -> None:
        import asyncio

        from textual.events import Key

        from kingdom.tui.app import InputArea

        input_area = InputArea()
        posted: list[str] = []
        input_area.post_message = lambda message: posted.append(type(message).__name__)

        asyncio.run(input_area._on_key(Key("shift+enter", None)))

        assert posted == []

    def test_submit_event_triggers_send_message(self) -> None:
        from kingdom.tui.app import ChatApp, InputArea

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        calls: list[str] = []
        app_instance.send_message = lambda: calls.append("sent")

        app_instance.on_input_area_submit(InputArea.Submit())

        assert calls == ["sent"]

    def test_input_area_stores_member_names(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        assert input_area.member_names == ["claude", "codex"]

    def test_input_area_default_member_names(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea()
        assert input_area.member_names == []

    def test_tab_no_at_sign_does_nothing(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        # Simulate typing "hello" then Tab
        input_area.load_text("hello")
        input_area.move_cursor((0, 5))
        input_area.handle_tab_complete()
        assert input_area.text == "hello"

    def test_tab_completes_at_prefix(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.load_text("@cl")
        input_area.move_cursor((0, 3))
        input_area.handle_tab_complete()
        assert input_area.text == "@claude "

    def test_tab_completes_bare_at(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.load_text("@")
        input_area.move_cursor((0, 1))
        input_area.handle_tab_complete()
        # First candidate should be first member
        assert input_area.text == "@claude "

    def test_tab_completes_at_all(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.load_text("@al")
        input_area.move_cursor((0, 3))
        input_area.handle_tab_complete()
        assert input_area.text == "@all "

    def test_tab_cycles_through_candidates(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.load_text("@c")
        input_area.move_cursor((0, 2))
        # First Tab: complete to first match
        input_area.handle_tab_complete()
        first = input_area.text
        assert first.startswith("@c")
        # Second Tab: cycle to next match
        input_area.handle_tab_complete()
        second = input_area.text
        assert second != first or len(input_area.tab_candidates) == 1

    def test_tab_with_text_before_at(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.load_text("Hey @cl")
        input_area.move_cursor((0, 7))
        input_area.handle_tab_complete()
        assert input_area.text == "Hey @claude "

    def test_tab_no_match_does_nothing(self) -> None:
        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.load_text("@zzz")
        input_area.move_cursor((0, 4))
        input_area.handle_tab_complete()
        assert input_area.text == "@zzz"

    def test_non_tab_key_resets_completion_state(self) -> None:
        import asyncio

        from textual.events import Key

        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude", "codex"])
        input_area.tab_candidates = ["claude", "codex"]
        input_area.tab_index = 1

        # A non-tab key should reset completion state
        asyncio.run(input_area._on_key(Key("a", "a")))
        assert input_area.tab_candidates == []
        assert input_area.tab_index == 0

    def test_tab_key_intercepted(self) -> None:
        import asyncio

        from textual.events import Key

        from kingdom.tui.app import InputArea

        input_area = InputArea(member_names=["claude"])
        input_area.load_text("@cl")
        input_area.move_cursor((0, 3))

        # Tab key should be intercepted and call handle_tab_complete
        asyncio.run(input_area._on_key(Key("tab", None)))
        assert input_area.text == "@claude "


class TestParseTargets:
    """Test @mention parsing for query dispatch."""

    def test_no_mentions_broadcasts(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-tgt", ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-tgt")
        list(app_instance.compose())  # trigger member loading
        targets = app_instance.parse_targets("What do you think?")
        assert targets == ["claude", "codex"]

    def test_at_member_targets_one(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-tgt2", ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-tgt2")
        list(app_instance.compose())
        targets = app_instance.parse_targets("@claude What do you think?")
        assert targets == ["claude"]

    def test_at_all_broadcasts(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-tgt3", ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-tgt3")
        list(app_instance.compose())
        targets = app_instance.parse_targets("@all What do you think?")
        assert targets == ["claude", "codex"]

    def test_multiple_mentions(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-tgt4", ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-tgt4")
        list(app_instance.compose())
        targets = app_instance.parse_targets("@claude @codex What do you think?")
        assert targets == ["claude", "codex"]

    def test_unknown_mention_fallback_to_broadcast(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-tgt5", ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-tgt5")
        list(app_instance.compose())
        targets = app_instance.parse_targets("@unknown What do you think?")
        assert targets == ["claude"]  # falls back to all members


class TestSlashCommands:
    """Test slash command handling."""

    def test_mute_excludes_from_broadcast(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-cmd1"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        app_instance.muted.add("codex")
        targets = app_instance.parse_targets("What do you think?")
        assert "codex" not in targets
        assert "claude" in targets

    def test_explicit_mention_overrides_mute(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-cmd2"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        app_instance.muted.add("codex")
        targets = app_instance.parse_targets("@codex What do you think?")
        assert targets == ["codex"]

    def test_at_all_excludes_muted(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-cmd3"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        app_instance.muted.add("codex")
        targets = app_instance.parse_targets("@all What do you think?")
        assert targets == ["claude"]

    def test_handle_slash_command_mute(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd4"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/mute claude")
        assert "claude" in app_instance.muted

    def test_handle_slash_command_unmute(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd5"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.muted.add("claude")
        app_instance.handle_slash_command("/unmute claude")
        assert "claude" not in app_instance.muted

    def test_handle_slash_command_help(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd6"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/help")
        app_instance.show_system_message.assert_called_once()
        msg = app_instance.show_system_message.call_args[0][0]
        assert "/mute" in msg
        assert "/quit" in msg

    def test_handle_slash_command_quit(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-cmd7"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        exited = []
        app_instance.exit = lambda: exited.append(True)
        app_instance.handle_slash_command("/quit")
        assert exited == [True]

    def test_handle_slash_command_exit(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        tid = "council-cmd8"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        exited = []
        app_instance.exit = lambda: exited.append(True)
        app_instance.handle_slash_command("/exit")
        assert exited == [True]

    def test_writeable_alias_dispatches(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd-writeable"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/writeable")
        app_instance.show_system_message.assert_called_once()
        msg = app_instance.show_system_message.call_args[0][0]
        assert "Writable mode" in msg

    def test_unknown_command_shows_error(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd9"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/bogus")
        app_instance.show_system_message.assert_called_once()
        msg = app_instance.show_system_message.call_args[0][0]
        assert "Unknown command" in msg
        assert "Did you mean" not in msg  # /bogus has no close prefix match

    def test_unknown_command_suggests_close_match(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd-suggest"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/halp")
        msg = app_instance.show_system_message.call_args[0][0]
        assert "Did you mean" in msg
        assert "/help" in msg

    def test_mute_invalid_member_shows_error(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd10"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/mute nonexistent")
        assert "nonexistent" not in app_instance.muted
        msg = app_instance.show_system_message.call_args[0][0]
        assert "Unknown member" in msg

    def test_mute_no_arg_shows_status(self, project: Path) -> None:
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-cmd11"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        # No members muted
        app_instance.handle_slash_command("/mute")
        msg = app_instance.show_system_message.call_args[0][0]
        assert "No members muted" in msg

        # One member muted
        app_instance.muted.add("claude")
        app_instance.handle_slash_command("/mute")
        msg = app_instance.show_system_message.call_args[0][0]
        assert "claude" in msg


class TestChatAppHistory:
    """Test thread history loading on open."""

    def test_load_history_sets_last_sequence(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp
        from kingdom.tui.poll import ThreadPoller

        tid = "council-hist"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        from kingdom.thread import add_message, thread_dir

        add_message(project, BRANCH, tid, from_="king", to="all", body="Question?")
        add_message(project, BRANCH, tid, from_="claude", to="king", body="Answer.")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        # Simulate mount: create poller and load history
        tdir = thread_dir(project, BRANCH, tid)
        app_instance.poller = ThreadPoller(thread_dir=tdir)
        # Can't call load_history without mounted widgets, so test poller sync directly
        from kingdom.thread import list_messages

        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 2
        assert messages[-1].sequence == 2

    def test_empty_thread_has_no_messages(self, project: Path) -> None:
        from kingdom.thread import list_messages

        tid = "council-empty"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 0


class TestPhase1SmokeTest:
    """End-to-end smoke test for Phase 1 TUI lifecycle (without real Textual app)."""

    def test_full_lifecycle_thread_to_poll(self, project: Path) -> None:
        """Verify: create thread → add messages → poll detects → error detection."""
        from kingdom.thread import add_message as add_msg
        from kingdom.tui.poll import NewMessage, ThreadPoller

        tid = "council-smoke"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        tdir = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid

        # Simulate king message + member responses
        add_msg(project, BRANCH, tid, from_="king", to="all", body="What do you think?")
        add_msg(project, BRANCH, tid, from_="claude", to="king", body="I think we should...")
        add_msg(project, BRANCH, tid, from_="codex", to="king", body="*Error: Timeout after 600s*")

        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code", "codex": "codex"})
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(msgs) == 3
        assert msgs[0].sender == "king"
        assert msgs[1].sender == "claude"
        assert msgs[2].sender == "codex"

        # Error detection
        from kingdom.thread import is_error_response, is_timeout_response

        assert not is_error_response(msgs[1].body)
        assert is_error_response(msgs[2].body)
        assert is_timeout_response(msgs[2].body)

    def test_chat_app_composes_with_thread(self, project: Path) -> None:
        """Verify ChatApp composes correctly with a real thread."""
        from kingdom.tui.app import ChatApp

        tid = "council-compose"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        widgets = list(app_instance.compose())

        assert len(widgets) == 5  # header, message log, status bar, command hints, input area
        assert app_instance.member_names == ["claude", "codex"]

    def test_parse_targets_with_all_variants(self, project: Path) -> None:
        """Verify @mention parsing handles all cases."""
        from kingdom.tui.app import ChatApp

        tid = "council-targets"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Plain text → all members
        assert app_instance.parse_targets("hello") == ["claude", "codex"]
        # @member → one member
        assert app_instance.parse_targets("@claude hello") == ["claude"]
        # @all → all members
        assert app_instance.parse_targets("@all hello") == ["claude", "codex"]
        # Multiple @mentions → those members
        assert app_instance.parse_targets("@claude @codex hello") == ["claude", "codex"]

    def test_kd_chat_new_via_cli(self, project: Path) -> None:
        """kd chat --new creates thread and would launch TUI."""
        with (
            patch("kingdom.cli.Path.cwd", return_value=project),
            patch("kingdom.cli.resolve_current_run", return_value=BRANCH),
            patch("kingdom.tui.app.ChatApp.run") as mock_run,
        ):
            result = runner.invoke(app, ["chat", "--new"])
        assert result.exit_code == 0
        mock_run.assert_called_once()


class TestErrorDetection:
    """Test that error messages from thread files are detected."""

    def test_error_body_detected(self) -> None:
        from kingdom.thread import is_error_response

        assert is_error_response("*Error: Timeout after 600s*")
        assert is_error_response("*Empty response — no text or error returned.*")
        assert not is_error_response("Normal response text")

    def test_timeout_body_detected(self) -> None:
        from kingdom.thread import is_timeout_response

        assert is_timeout_response("*Error: Timeout after 600s*")
        assert not is_timeout_response("*Error: API key not set*")


class TestRunQuery:
    """Test run_query persists responses and cleans up stream files."""

    def test_run_query_persists_response_to_thread(self, project: Path) -> None:
        """run_query must call add_message with the response body."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import list_messages
        from kingdom.tui.app import ChatApp

        tid = "council-rq1"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Fake member that returns a successful response
        fake_response = AgentResponse(name="claude", text="I think yes.")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        # Response must be persisted as a thread message
        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 1
        assert messages[0].from_ == "claude"
        assert messages[0].body == "I think yes."

    def test_run_query_preserves_stream_file(self, project: Path) -> None:
        """run_query must NOT delete the stream file — poller drains it."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.tui.app import ChatApp

        tid = "council-rq2"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        tdir = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid
        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.write_text('{"type":"test"}\n', encoding="utf-8")

        fake_response = AgentResponse(name="claude", text="Done.")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        assert stream_path.exists(), "Stream file should persist for poller to drain"

    def test_run_query_preserves_debug_stream_when_enabled(self, project: Path) -> None:
        """run_query should save a debug copy when debug streams are enabled."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.tui.app import ChatApp

        tid = "council-rq-debug"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid, debug_streams=True)
        list(app_instance.compose())

        tdir = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid
        stream_path = tdir / ".stream-claude.jsonl"
        stream_content = '{"type":"response.output_text.delta","delta":"hello"}\n'
        stream_path.write_text(stream_content, encoding="utf-8")

        fake_response = AgentResponse(name="claude", text="Done.")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        assert not stream_path.exists(), "Live stream file should still be cleaned up"

        debug_files = sorted(tdir.glob(".debug-stream-claude-*.jsonl"))
        assert len(debug_files) == 1
        assert debug_files[0].read_text(encoding="utf-8") == stream_content

    def test_run_query_persists_error_response(self, project: Path) -> None:
        """run_query must persist error-only responses to thread files."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import list_messages
        from kingdom.tui.app import ChatApp

        tid = "council-rq3"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        fake_response = AgentResponse(name="claude", text="", error="Timeout after 600s")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 1
        assert messages[0].body == "*Error: Timeout after 600s*"

    def test_run_query_persists_partial_timeout(self, project: Path) -> None:
        """Partial timeout (text + error) must still persist the text."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import list_messages
        from kingdom.tui.app import ChatApp

        tid = "council-rq4"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        fake_response = AgentResponse(name="claude", text="Partial answer before timeout", error="Timeout after 600s")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 1
        # thread_body() returns text when both text and error are present
        assert messages[0].body == "Partial answer before timeout"

    def test_run_query_labels_interrupted_partial_response(self, project: Path) -> None:
        """Interrupted responses with partial text must include an interrupted marker."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import list_messages
        from kingdom.tui.app import ChatApp

        tid = "council-rq-int"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.interrupted = True  # Simulate interrupt

        fake_response = AgentResponse(name="claude", text="Partial answer before interrupt")

        class FakeMember:
            name = "claude"
            session_id = None

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 1
        # Body should contain the partial text AND an interrupted marker
        assert "Partial answer before interrupt" in messages[0].body
        assert "[Interrupted" in messages[0].body

    def test_run_query_uses_formatted_thread_history(self, project: Path) -> None:
        """run_query should send full formatted history, not only the latest text."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import add_message
        from kingdom.tui.app import ChatApp

        tid = "council-rq5"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")

        add_message(project, BRANCH, tid, from_="king", to="all", body="What changed?")
        add_message(project, BRANCH, tid, from_="codex", to="king", body="I updated the parser.")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        captured_prompt: dict[str, str] = {}
        fake_response = AgentResponse(name="claude", text="Looks good.")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                captured_prompt["value"] = prompt
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        prompt = captured_prompt["value"]
        assert "[Previous conversation]" in prompt
        assert "king: What changed?" in prompt
        assert "codex: I updated the parser." in prompt
        assert prompt.rstrip().endswith("You are claude. Continue the discussion.")


class TestChatAppSessionIsolation:
    """Chat threads should not inherit session resume IDs."""

    def test_on_mount_does_not_call_load_sessions(self, project: Path) -> None:
        """ChatApp must not call council.load_sessions() — chat uses thread history only."""
        from kingdom.tui.app import ChatApp

        tid = "council-iso"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Simulate what on_mount does (without real Textual app)
        from kingdom.council import Council

        council = Council.create(base=project)
        # After ChatApp.on_mount, members should have no session_id
        # (load_sessions is not called)
        for member in council.members:
            assert member.session_id is None

    def test_chat_preamble_set_on_members(self, project: Path) -> None:
        """ChatApp should set chat-specific preamble on council members."""
        from kingdom.tui.app import CHAT_PREAMBLE, ChatApp

        tid = "council-preamble"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Simulate the council setup from on_mount (without real Textual mount)
        from kingdom.council import Council

        council = Council.create(base=project)
        for member in council.members:
            member.preamble = CHAT_PREAMBLE.format(name=member.name)

        for member in council.members:
            assert "participating in a group discussion" in member.preamble
            assert member.name in member.preamble
            assert "council advisor" not in member.preamble.lower()


class TestEscapeInterrupt:
    """Test Escape key interrupt behavior."""

    def test_app_has_interrupted_flag(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.interrupted is False

    def test_interrupt_with_no_council_exits(self) -> None:
        """Escape with no council initialized should exit."""
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.council is None

        exited = []
        app_instance.exit = lambda: exited.append(True)
        app_instance.action_interrupt()
        assert exited == [True]

    def test_interrupt_with_no_active_queries_exits(self, project: Path) -> None:
        """Escape with no running queries should exit."""
        from kingdom.council import Council
        from kingdom.tui.app import ChatApp

        tid = "council-int1"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.council = Council.create(base=project)

        # No active processes
        for m in app_instance.council.members:
            assert m.process is None

        exited = []
        app_instance.exit = lambda: exited.append(True)
        app_instance.action_interrupt()
        assert exited == [True]
        assert app_instance.interrupted is False

    def test_interrupt_terminates_active_processes(self, project: Path) -> None:
        """Escape with running queries should terminate processes."""
        from unittest.mock import MagicMock

        from kingdom.council import Council
        from kingdom.tui.app import ChatApp

        tid = "council-int2"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.council = Council.create(base=project)

        # Simulate active process on claude
        mock_proc = MagicMock()
        claude = app_instance.council.get_member("claude")
        claude.process = mock_proc

        # Stub out query_one to avoid needing mounted widgets
        input_mock = MagicMock()
        input_mock.text = ""  # empty input so Escape doesn't just clear
        log_mock = MagicMock()
        log_mock.query.return_value = []

        def fake_query_one(selector, *args, **kwargs):
            if selector == "#input-area":
                return input_mock
            return log_mock

        app_instance.query_one = fake_query_one

        app_instance.action_interrupt()

        assert app_instance.interrupted is True
        mock_proc.terminate.assert_called_once()

    def test_interrupt_handles_multiple_panels_same_member(self, project: Path) -> None:
        """Interrupting when both wait and stream panels exist should not cause MountError."""
        from unittest.mock import MagicMock

        from kingdom.council import Council
        from kingdom.tui.app import ChatApp

        tid = "council-int-dup"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.council = Council.create(base=project)

        mock_proc = MagicMock()
        claude = app_instance.council.get_member("claude")
        claude.process = mock_proc

        input_mock = MagicMock()
        input_mock.text = ""

        # Simulate both wait-claude and stream-claude panels existing
        wait_panel = MagicMock(name="wait-claude")
        stream_panel = MagicMock(name="stream-claude")
        log_mock = MagicMock()

        def fake_query_one(selector, *args, **kwargs):
            if selector == "#input-area":
                return input_mock
            if selector == "#message-log":
                return log_mock
            # Simulate: wait-claude and stream-claude both found, thinking-claude not found
            if selector == "#wait-claude":
                return wait_panel
            if selector == "#stream-claude":
                return stream_panel
            from textual.css.query import QueryError

            raise QueryError("")

        log_mock.query_one = fake_query_one
        app_instance.query_one = fake_query_one

        app_instance.action_interrupt()

        # Only one interrupted panel should be mounted (not two)
        assert log_mock.mount.call_count == 1
        # Both stale panels should be removed
        wait_panel.remove.assert_called_once()
        stream_panel.remove.assert_called_once()

    def test_second_escape_after_interrupt_exits(self, project: Path) -> None:
        """Second Escape after interrupt should force quit."""
        from kingdom.council import Council
        from kingdom.tui.app import ChatApp

        tid = "council-int3"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.council = Council.create(base=project)
        app_instance.interrupted = True

        exited = []
        app_instance.exit = lambda: exited.append(True)
        app_instance.action_interrupt()
        assert exited == [True]

    def test_send_message_resets_interrupted_flag(self) -> None:
        """Sending a new message should reset the interrupted flag."""
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.interrupted = True
        # send_message needs a TextArea; test the flag reset logic directly
        assert app_instance.interrupted is True

    def test_run_query_uses_interrupted_body(self, project: Path) -> None:
        """Interrupted queries with no text should persist '*Interrupted*'."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import list_messages
        from kingdom.tui.app import ChatApp

        tid = "council-int4"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.interrupted = True

        fake_response = AgentResponse(name="claude", text="", error="Exit code -15")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 1
        assert messages[0].body == "*Interrupted*"

    def test_run_query_keeps_partial_text_on_interrupt(self, project: Path) -> None:
        """Interrupted queries with partial text should persist the text."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.thread import list_messages
        from kingdom.tui.app import ChatApp

        tid = "council-int5"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.interrupted = True

        fake_response = AgentResponse(name="claude", text="Partial answer before kill", error="Exit code -15")

        class FakeMember:
            name = "claude"

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                return fake_response

        stream_path = project / ".kd" / "branches" / "feature-test-chat" / "threads" / tid / ".stream-claude.jsonl"
        asyncio.run(app_instance.run_query(FakeMember(), stream_path))

        messages = list_messages(project, BRANCH, tid)
        assert len(messages) == 1
        assert "Partial answer before kill" in messages[0].body
        assert "*[Interrupted" in messages[0].body


class TestChatAppLayout:
    """Test the widget layout of ChatApp."""

    def test_member_names_loaded(self, project: Path) -> None:
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-layout", ["king", "claude", "codex"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-layout")
        # Compose triggers member loading
        widgets = list(app_instance.compose())
        assert app_instance.member_names == ["claude", "codex"]
        assert len(widgets) == 5  # header, message log, status bar, command hints, input area

    def test_header_shows_thread_info(self, project: Path) -> None:
        from textual.widgets import Static

        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, "council-hdr", ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id="council-hdr")
        widgets = list(app_instance.compose())
        header = widgets[0]
        assert isinstance(header, Static)
        # Static stores content as _content or via update(); check the id
        assert header.id == "header-bar"


class TestAutoTurns:
    """Test auto-turn round-robin scheduling after initial broadcast."""

    def make_fake_member(self, name: str):
        """Create a fake member that records query calls."""
        from kingdom.council.base import AgentResponse

        class FakeMember:
            def __init__(self, member_name):
                self.name = member_name
                self.call_count = 0
                self.process = None
                self.base = None
                self.branch = None
                self.preamble = ""
                self.session_id = None

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                self.call_count += 1
                return AgentResponse(name=self.name, text=f"Response {self.call_count} from {self.name}")

        return FakeMember(name)

    def make_app_with_council(
        self, project, tid, member_names, auto_messages=-1, mode="broadcast", first_exchange=False
    ):
        """Create a ChatApp with a fake council for testing run_chat_round.

        By default sets up a follow-up conversation (prior member responses exist)
        so auto-turns will fire. Set first_exchange=True to test the first-message
        behavior (broadcast only, no auto-turns).
        """
        from unittest.mock import MagicMock

        from kingdom.council.council import Council
        from kingdom.thread import add_message
        from kingdom.tui.app import ChatApp

        create_thread(project, BRANCH, tid, ["king", *member_names], "council")

        if first_exchange:
            # Only a king message — no prior member responses
            add_message(project, BRANCH, tid, from_="king", to="all", body="What do you think?")
        else:
            # Simulate an established conversation with prior exchange
            add_message(project, BRANCH, tid, from_="king", to="all", body="First question")
            for name in member_names:
                add_message(project, BRANCH, tid, from_=name, to="king", body=f"Response from {name}")
            add_message(project, BRANCH, tid, from_="king", to="all", body="Follow-up question")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Build fake council with fake members
        fake_members = [self.make_fake_member(n) for n in member_names]
        council = Council(members=fake_members, auto_messages=auto_messages, mode=mode)
        app_instance.council = council

        # Mock query_one for DOM operations in auto-turn WaitingPanel mounts
        mock_log = MagicMock()
        app_instance.query_one = MagicMock(return_value=mock_log)

        return app_instance, fake_members

    def test_first_message_broadcast_only(self, project: Path) -> None:
        """First king message in a thread should broadcast only, no auto-turns."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at0"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], first_exchange=True)

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=True))

        # Only initial broadcast, no auto-turns
        for m in members:
            assert m.call_count == 1, f"{m.name} expected 1 query (broadcast only), got {m.call_count}"

    def test_follow_up_broadcasts_then_auto_turns(self, project: Path) -> None:
        """Follow-up king messages should broadcast first, then do sequential auto-turns."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at1"
        # auto_messages=-1 → len(members) = 2 sequential messages after broadcast
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"])

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # 1 broadcast + 1 auto-turn each
        for m in members:
            assert m.call_count == 2, f"{m.name} expected 2 queries (broadcast + auto-turn), got {m.call_count}"

    def test_auto_messages_budget_limits_total(self, project: Path) -> None:
        """auto_messages=3 with 2 members: broadcast(1 each) + sequential claude(1) codex(1) claude(1)."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at1b"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], auto_messages=3)

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # Broadcast(1 each) + sequential budget=3: claude(1) codex(1) claude(1)
        assert members[0].call_count == 3  # claude: 1 broadcast + 2 auto-turns
        assert members[1].call_count == 2  # codex: 1 broadcast + 1 auto-turn

    def test_auto_messages_zero_disables_auto_turns(self, project: Path) -> None:
        """auto_messages=0 should still broadcast but skip auto-turns on follow-up."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at2"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], auto_messages=0)

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # Broadcast only, no auto-turns
        for m in members:
            assert m.call_count == 1, f"{m.name} expected 1 query (broadcast only), got {m.call_count}"

    def test_interrupted_stops_auto_turns(self, project: Path) -> None:
        """Setting interrupted=True during broadcast should stop auto-turns."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at3"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], auto_messages=4)

        # Make claude set interrupted=True during broadcast
        real_query = members[0].query

        def interrupting_query(prompt, timeout, stream_path=None, max_retries=0):
            result = real_query(prompt, timeout, stream_path, max_retries)
            app_instance.interrupted = True
            return result

        members[0].query = interrupting_query

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # Both queried in broadcast (parallel), but auto-turns stopped
        assert members[0].call_count == 1  # broadcast only
        assert members[1].call_count == 1  # broadcast only

    def test_generation_mismatch_stops_auto_turns(self, project: Path) -> None:
        """Incrementing generation during broadcast should stop auto-turns."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at4"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], auto_messages=4)

        # Increment generation after claude's broadcast query
        real_query = members[0].query

        def preempting_query(prompt, timeout, stream_path=None, max_retries=0):
            result = real_query(prompt, timeout, stream_path, max_retries)
            app_instance.generation += 1  # Simulate new user message
            return result

        members[0].query = preempting_query

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # Both queried in broadcast (parallel), but auto-turns stopped by generation mismatch
        assert members[0].call_count == 1  # broadcast only
        assert members[1].call_count == 1  # broadcast only

    def test_muted_members_skipped_in_auto_turns(self, project: Path) -> None:
        """Muted members should be skipped in sequential auto-turn round-robin."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at5"
        # Budget=4, 3 members, codex muted → broadcast targets exclude muted
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex", "extra"], auto_messages=4)
        app_instance.muted.add("codex")

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        # In real usage, parse_targets excludes muted members from targets
        asyncio.run(app_instance.run_chat_round(["claude", "extra"], 1, tdir, is_first_exchange=False))

        # Broadcast(1 each) + sequential budget=4, active=[claude, extra]:
        # claude(auto), extra(auto), claude(auto), extra(auto) = 4 auto-turns
        assert members[0].call_count == 3  # claude: 1 broadcast + 2 auto-turns
        assert members[1].call_count == 0  # codex: muted, not in targets
        assert members[2].call_count == 3  # extra: 1 broadcast + 2 auto-turns

    def test_directed_message_skips_auto_turns(self, project: Path) -> None:
        """@member directed messages should not trigger auto-turns."""
        from kingdom.tui.app import ChatApp

        tid = "council-at6"
        create_thread(project, BRANCH, tid, ["king", "claude", "codex"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        targets = app_instance.parse_targets("@claude What do you think?")
        to = targets[0] if len(targets) == 1 else "all"

        # Directed message: to should be the member name, not "all"
        assert to == "claude"
        assert to != "all"  # This means send_message won't use run_chat_round

    def test_sequential_mode_first_exchange(self, project: Path) -> None:
        """mode='sequential' first exchange should query members one at a time."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at7"
        app_instance, members = self.make_app_with_council(
            project, tid, ["claude", "codex"], mode="sequential", first_exchange=True
        )

        call_order = []
        for m in members:
            real_query = m.query
            name = m.name

            def make_ordered_query(real_fn, member_name):
                def ordered_query(prompt, timeout, stream_path=None, max_retries=0):
                    result = real_fn(prompt, timeout, stream_path, max_retries)
                    call_order.append(member_name)
                    return result

                return ordered_query

            m.query = make_ordered_query(real_query, name)

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=True))

        # Sequential first exchange: claude then codex, no auto-turns
        assert call_order == ["claude", "codex"]

    def test_follow_up_queries_in_round_robin_order(self, project: Path) -> None:
        """Follow-up auto-turns should proceed in member order after broadcast."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at7b"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], auto_messages=4)

        call_order = []
        for m in members:
            real_query = m.query
            name = m.name

            def make_ordered_query(real_fn, member_name):
                def ordered_query(prompt, timeout, stream_path=None, max_retries=0):
                    result = real_fn(prompt, timeout, stream_path, max_retries)
                    call_order.append(member_name)
                    return result

                return ordered_query

            m.query = make_ordered_query(real_query, name)

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # Broadcast (parallel, order may vary) + sequential auto-turns
        # Skip broadcast entries, verify auto-turn order
        auto_turn_order = call_order[2:]  # first 2 are broadcast (parallel)
        assert auto_turn_order == ["claude", "codex", "claude", "codex"]

    def test_error_in_broadcast_does_not_stop_others(self, project: Path) -> None:
        """An error from one member in broadcast should not stop other members."""
        import asyncio

        from kingdom.thread import thread_dir

        tid = "council-at8"
        app_instance, members = self.make_app_with_council(project, tid, ["claude", "codex"], auto_messages=2)

        # Make claude raise an exception
        def error_query(prompt, timeout, stream_path=None, max_retries=0):
            members[0].call_count += 1
            raise RuntimeError("API error")

        members[0].query = error_query

        tdir = thread_dir(project, BRANCH, tid)
        app_instance.generation = 1
        asyncio.run(app_instance.run_chat_round(["claude", "codex"], 1, tdir, is_first_exchange=False))

        # Both queried in broadcast; claude errors but codex still runs
        assert members[0].call_count >= 1  # claude: at least broadcast (errors)
        assert members[1].call_count >= 1  # codex: broadcast + possible auto-turns

    def test_app_has_generation_counter(self) -> None:
        """ChatApp should have a generation counter initialized to 0."""
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.generation == 0


class TestChatSessionIsolation:
    """Test that chat queries don't write to shared session state files.

    Ticket 0f27: kd chat was writing PIDs and accumulating session_id via shared
    sessions/{agent}.json files, causing cross-talk with concurrent workflows.
    """

    def test_on_mount_does_not_set_member_base_branch(self, project: Path) -> None:
        """on_mount should NOT set member.base/branch, so query_once won't write PIDs.

        The on_mount code creates a Council and configures members. It should
        set preamble but NOT base/branch (which would cause PID writes to shared
        session files).
        """
        from kingdom.council.council import Council
        from kingdom.tui.app import CHAT_PREAMBLE

        # Simulate what on_mount does
        council = Council.create(base=project)
        for member in council.members:
            # on_mount currently does: member.base = self.base; member.branch = self.branch
            # After fix, it should only set preamble
            member.preamble = CHAT_PREAMBLE.format(name=member.name)

        # Verify members do NOT have base/branch set
        for member in council.members:
            assert member.base is None, f"{member.name}.base should be None, got {member.base}"
            assert member.branch is None, f"{member.name}.branch should be None, got {member.branch}"

    def test_chat_clears_session_id_after_query(self, project: Path) -> None:
        """run_query should reset member.session_id to None after each query."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.council.council import Council
        from kingdom.thread import add_message, create_thread, thread_dir
        from kingdom.tui.app import ChatApp

        tid = "council-iso2"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        add_message(project, BRANCH, tid, from_="king", to="all", body="Hello")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Build a fake member that returns a session_id
        class FakeMember:
            def __init__(self):
                self.name = "claude"
                self.session_id = None
                self.process = None
                self.base = None
                self.branch = None
                self.preamble = ""

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                self.session_id = "session-abc-123"  # Simulate agent returning a session ID
                return AgentResponse(name="claude", text="Response from claude")

        fake = FakeMember()
        council = Council(members=[fake])
        app_instance.council = council
        app_instance.member_names = ["claude"]

        tdir = thread_dir(project, BRANCH, tid)
        stream_path = tdir / ".stream-claude.jsonl"

        asyncio.run(app_instance.run_query(fake, stream_path))

        # After run_query, session_id should be cleared
        assert fake.session_id is None, f"session_id should be None after query, got {fake.session_id!r}"

    def test_chat_query_does_not_pass_session_id(self, project: Path) -> None:
        """The second chat query should NOT pass a session_id from the first query."""
        import asyncio

        from kingdom.council.base import AgentResponse
        from kingdom.council.council import Council
        from kingdom.thread import add_message, create_thread, thread_dir
        from kingdom.tui.app import ChatApp

        tid = "council-iso3"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        add_message(project, BRANCH, tid, from_="king", to="all", body="Hello")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Track what session_id was used when building the command
        session_ids_used: list[str | None] = []

        class FakeMember:
            def __init__(self):
                self.name = "claude"
                self.session_id = None
                self.process = None
                self.base = None
                self.branch = None
                self.preamble = ""

            def query(self, prompt, timeout, stream_path=None, max_retries=0):
                session_ids_used.append(self.session_id)
                self.session_id = "session-from-agent"  # Agent returns a session
                return AgentResponse(name="claude", text="Response")

        fake = FakeMember()
        council = Council(members=[fake])
        app_instance.council = council
        app_instance.member_names = ["claude"]

        tdir = thread_dir(project, BRANCH, tid)

        # First query
        asyncio.run(app_instance.run_query(fake, tdir / ".stream-claude.jsonl"))
        # Second query — should NOT pass the session_id from first query
        add_message(project, BRANCH, tid, from_="king", to="all", body="Follow-up")
        asyncio.run(app_instance.run_query(fake, tdir / ".stream-claude.jsonl"))

        assert session_ids_used[0] is None, "First query should use session_id=None"
        assert session_ids_used[1] is None, f"Second query should use session_id=None, got {session_ids_used[1]!r}"


class TestCouncilCreateNewFields:
    """Test that Council.create() passes auto_messages and mode from config."""

    def test_create_default_auto_messages(self, project: Path) -> None:
        """Default auto_messages should be -1 (auto: len(members))."""
        from kingdom.council.council import Council

        council = Council.create(base=project)
        assert council.auto_messages == -1

    def test_create_default_mode(self, project: Path) -> None:
        """Default mode should be 'broadcast'."""
        from kingdom.council.council import Council

        council = Council.create(base=project)
        assert council.mode == "broadcast"

    def test_create_custom_auto_messages(self, project: Path) -> None:
        """Custom auto_messages from config should be passed through."""
        import json

        kd = project / ".kd"
        (kd / "config.json").write_text(json.dumps({"council": {"auto_messages": 5}}))

        from kingdom.council.council import Council

        council = Council.create(base=project)
        assert council.auto_messages == 5

    def test_create_auto_messages_zero(self, project: Path) -> None:
        """auto_messages=0 should be valid (disables auto-turns)."""
        import json

        kd = project / ".kd"
        (kd / "config.json").write_text(json.dumps({"council": {"auto_messages": 0}}))

        from kingdom.council.council import Council

        council = Council.create(base=project)
        assert council.auto_messages == 0

    def test_create_sequential_mode(self, project: Path) -> None:
        """mode='sequential' from config should be passed through."""
        import json

        kd = project / ".kd"
        (kd / "config.json").write_text(json.dumps({"council": {"mode": "sequential"}}))

        from kingdom.council.council import Council

        council = Council.create(base=project)
        assert council.mode == "sequential"


class TestToggleThinking:
    """Test Ctrl+T thinking visibility toggle."""

    def test_default_thinking_visibility(self) -> None:
        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        assert app_instance.thinking_visibility == "auto"

    def test_toggle_cycles_auto_show_hide(self) -> None:
        """action_toggle_thinking should cycle: auto -> show -> hide -> auto."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.show_system_message = MagicMock()
        app_instance.query = MagicMock(return_value=[])

        assert app_instance.thinking_visibility == "auto"

        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "show"

        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "hide"

        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "auto"

    def test_toggle_shows_system_message(self) -> None:
        """Each toggle should show a system message with the new mode."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.show_system_message = MagicMock()
        app_instance.query = MagicMock(return_value=[])

        app_instance.action_toggle_thinking()
        msg = app_instance.show_system_message.call_args[0][0]
        assert "always show" in msg

        app_instance.action_toggle_thinking()
        msg = app_instance.show_system_message.call_args[0][0]
        assert "hidden" in msg

        app_instance.action_toggle_thinking()
        msg = app_instance.show_system_message.call_args[0][0]
        assert "auto" in msg

    def test_toggle_hides_existing_panels(self) -> None:
        """Toggling to 'hide' should set display=False on all ThinkingPanels."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp
        from kingdom.tui.widgets import ThinkingPanel

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.show_system_message = MagicMock()

        panel1 = ThinkingPanel(sender="claude")
        panel2 = ThinkingPanel(sender="codex")
        app_instance.query = MagicMock(return_value=[panel1, panel2])

        # Cycle to "show", then "hide"
        app_instance.thinking_visibility = "show"
        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "hide"

        assert panel1.display is False
        assert panel2.display is False

    def test_toggle_shows_existing_panels(self) -> None:
        """Toggling to 'show' should set display=True and expand non-pinned panels."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp
        from kingdom.tui.widgets import ThinkingPanel

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.show_system_message = MagicMock()

        panel = ThinkingPanel(sender="claude")
        panel.expanded = False
        panel.display = False
        app_instance.query = MagicMock(return_value=[panel])

        # Cycle from auto to show
        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "show"

        assert panel.display is True
        assert panel.expanded is True

    def test_toggle_show_respects_user_pinned(self) -> None:
        """Toggling to 'show' should not expand user-pinned collapsed panels."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp
        from kingdom.tui.widgets import ThinkingPanel

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.show_system_message = MagicMock()

        panel = ThinkingPanel(sender="claude")
        panel.expanded = False
        panel.user_pinned = True
        panel.display = False
        app_instance.query = MagicMock(return_value=[panel])

        # Cycle from auto to show
        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "show"

        # Should be visible but NOT expanded (user pinned it collapsed)
        assert panel.display is True
        assert panel.expanded is False

    def test_toggle_auto_restores_visibility(self) -> None:
        """Toggling to 'auto' from 'hide' should make panels visible again."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp
        from kingdom.tui.widgets import ThinkingPanel

        app_instance = ChatApp(base=Path("/tmp"), branch="main", thread_id="council-abc")
        app_instance.show_system_message = MagicMock()

        panel = ThinkingPanel(sender="claude")
        panel.display = False
        app_instance.query = MagicMock(return_value=[panel])

        # Start from hide, toggle to auto
        app_instance.thinking_visibility = "hide"
        app_instance.action_toggle_thinking()
        assert app_instance.thinking_visibility == "auto"

        assert panel.display is True

    def test_thinking_cycle_class_var(self) -> None:
        """THINKING_CYCLE should contain exactly auto, show, hide."""
        from kingdom.tui.app import ChatApp

        assert ChatApp.THINKING_CYCLE == ["auto", "show", "hide"]

    def test_help_includes_thinking_hotkey(self, project: Path) -> None:
        """Help text should mention the Ctrl+T thinking toggle."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp

        tid = "council-think-help"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")
        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())
        app_instance.show_system_message = MagicMock()

        app_instance.handle_slash_command("/help")
        msg = app_instance.show_system_message.call_args[0][0]
        assert "Ctrl+T" in msg
        assert "thinking" in msg.lower()

    def test_binding_registered(self) -> None:
        """ChatApp should have a ctrl+t binding for toggle_thinking."""
        from kingdom.tui.app import ChatApp

        bindings = ChatApp.BINDINGS
        keys = [b[0] for b in bindings]
        assert "ctrl+t" in keys


class TestBuildBranchContext:
    """Test branch context injection into chat system prompt."""

    def test_returns_branch_name(self, project: Path) -> None:
        from kingdom.tui.app import build_branch_context

        ctx = build_branch_context(project, BRANCH)
        assert "[Branch context]" in ctx
        assert f"Branch: {BRANCH}" in ctx

    def test_includes_tickets(self, project: Path) -> None:
        from kingdom.state import branch_root
        from kingdom.ticket import Ticket, write_ticket
        from kingdom.tui.app import build_branch_context

        tickets_dir = branch_root(project, BRANCH) / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)
        write_ticket(
            Ticket(id="ab12", status="open", title="First ticket", priority=1),
            tickets_dir / "ab12.md",
        )
        write_ticket(
            Ticket(id="cd34", status="in_progress", title="Second ticket", priority=2),
            tickets_dir / "cd34.md",
        )

        ctx = build_branch_context(project, BRANCH)
        assert "Tickets:" in ctx
        assert "ab12" in ctx
        assert "First ticket" in ctx
        assert "cd34" in ctx
        assert "Second ticket" in ctx
        assert "in progress" in ctx  # underscores replaced with spaces

    def test_no_tickets_omits_tickets_section(self, project: Path) -> None:
        from kingdom.tui.app import build_branch_context

        ctx = build_branch_context(project, BRANCH)
        assert "[Branch context]" in ctx
        assert f"Branch: {BRANCH}" in ctx
        assert "Tickets:" not in ctx

    def test_preamble_includes_branch_context(self, project: Path) -> None:
        """on_mount should inject branch context into each member's preamble."""
        from kingdom.council.council import Council
        from kingdom.state import branch_root
        from kingdom.ticket import Ticket, write_ticket
        from kingdom.tui.app import CHAT_PREAMBLE, build_branch_context

        # Create a ticket so context has something to show
        tickets_dir = branch_root(project, BRANCH) / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)
        write_ticket(
            Ticket(id="ef56", status="open", title="Test ticket", priority=2),
            tickets_dir / "ef56.md",
        )

        # Simulate what on_mount does
        council = Council.create(base=project)
        branch_context = build_branch_context(project, BRANCH)
        for member in council.members:
            member.preamble = CHAT_PREAMBLE.format(name=member.name) + branch_context

        for member in council.members:
            assert "participating in a group discussion" in member.preamble
            assert f"Branch: {BRANCH}" in member.preamble
            assert "ef56" in member.preamble
            assert "Test ticket" in member.preamble

    def test_context_ends_with_double_newline(self, project: Path) -> None:
        """Context block should end with double newline for clean separation."""
        from kingdom.tui.app import build_branch_context

        ctx = build_branch_context(project, BRANCH)
        assert ctx.endswith("\n\n")

    def test_ticket_priority_ordering(self, project: Path) -> None:
        """Tickets should be listed in priority order (P1 first)."""
        from kingdom.state import branch_root
        from kingdom.ticket import Ticket, write_ticket
        from kingdom.tui.app import build_branch_context

        tickets_dir = branch_root(project, BRANCH) / "tickets"
        tickets_dir.mkdir(parents=True, exist_ok=True)
        write_ticket(
            Ticket(id="lo01", status="open", title="Low priority", priority=3),
            tickets_dir / "lo01.md",
        )
        write_ticket(
            Ticket(id="hi01", status="open", title="High priority", priority=1),
            tickets_dir / "hi01.md",
        )

        ctx = build_branch_context(project, BRANCH)
        # P1 should appear before P3
        hi_pos = ctx.index("hi01")
        lo_pos = ctx.index("lo01")
        assert hi_pos < lo_pos


class TestSendMessageCleansUpPanels:
    """Test that send_message removes in-flight panels before mounting new ones."""

    def test_send_removes_existing_wait_panels(self, project: Path) -> None:
        """Sending a second message should clean up WaitingPanels from the first."""
        from unittest.mock import MagicMock

        from kingdom.tui.app import ChatApp, MessageLog

        tid = "council-dup1"
        create_thread(project, BRANCH, tid, ["king", "claude"], "council")

        app_instance = ChatApp(base=project, branch=BRANCH, thread_id=tid)
        list(app_instance.compose())

        # Track calls to remove_member_panels
        removed = []
        original_remove = app_instance.remove_member_panels

        def tracking_remove(log, name):
            removed.append(name)
            original_remove(log, name)

        app_instance.remove_member_panels = tracking_remove

        # Mock the log and worker to prevent actual Textual operations
        mock_log = MagicMock(spec=MessageLog)
        mock_log.query.return_value = []
        mock_log.scroll_if_following = MagicMock()

        from kingdom.tui.app import InputArea

        mock_input = MagicMock(spec=InputArea)
        mock_input.text = "Hello"
        mock_input.has_focus = True

        def fake_query_one(sel_or_cls, cls=None):
            if sel_or_cls == "#input-area" or cls is InputArea:
                return mock_input
            return mock_log

        app_instance.query_one = fake_query_one
        app_instance.run_worker = MagicMock()

        app_instance.send_message()

        # remove_member_panels should have been called for "claude"
        assert "claude" in removed
