"""Tests for ThinkingPanel persistence in ChatApp."""

from unittest.mock import MagicMock, Mock

from kingdom.tui.app import ChatApp
from kingdom.tui.poll import NewMessage
from kingdom.tui.widgets import MessagePanel, StreamingPanel, ThinkingPanel


class TestThinkingPersistence:
    def test_handle_new_message_replaces_thinking_panel(self) -> None:
        """handle_new_message should remove old ThinkingPanel and mount a new one with sequence id."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "auto"

        log = MagicMock()

        # Setup existing panels: ThinkingPanel and StreamingPanel
        thinking_panel = MagicMock(spec=ThinkingPanel)
        thinking_panel.thinking_text = "reasoning text"
        thinking_panel.start_time = 1000.0
        thinking_panel.user_pinned = False
        thinking_panel.expanded = True
        streaming_panel = MagicMock(spec=StreamingPanel)

        # Mock query results
        def query_side_effect(selector):
            if "thinking-claude" in selector:
                return [thinking_panel]
            if "stream-claude" in selector:
                return [streaming_panel]
            return []

        log.query.side_effect = query_side_effect

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        # Old ThinkingPanel should be removed
        thinking_panel.remove.assert_called_once()

        # StreamingPanel should also be removed
        streaming_panel.remove.assert_called_once()

        # Two mounts: new ThinkingPanel (before old) + MessagePanel (before streaming)
        assert log.mount.call_count == 2
        mount_calls = log.mount.call_args_list
        # First mount: new ThinkingPanel before old thinking panel
        new_tp = mount_calls[0][0][0]
        assert isinstance(new_tp, ThinkingPanel)
        assert new_tp.thinking_text == "reasoning text"
        # Second mount: MessagePanel
        msg = mount_calls[1][0][0]
        assert isinstance(msg, MessagePanel)

    def test_handle_new_message_mounts_at_end_if_no_streaming(self) -> None:
        """If only ThinkingPanel exists (no streaming), mount MessagePanel at end."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "auto"

        log = MagicMock()

        thinking_panel = MagicMock(spec=ThinkingPanel)
        thinking_panel.thinking_text = "reasoning"
        thinking_panel.start_time = 1000.0
        thinking_panel.user_pinned = False
        thinking_panel.expanded = True

        # Only ThinkingPanel exists
        def query_side_effect(selector):
            if "thinking-claude" in selector:
                return [thinking_panel]
            return []

        log.query.side_effect = query_side_effect

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        # Old ThinkingPanel removed, new one mounted
        thinking_panel.remove.assert_called_once()

        # Two mounts: new ThinkingPanel + MessagePanel
        assert log.mount.call_count == 2
        # MessagePanel should be mounted at end (no 'before' arg) since no streaming panel
        msg_mount = log.mount.call_args_list[1]
        assert isinstance(msg_mount[0][0], MessagePanel)
        assert "before" not in msg_mount[1]

    def test_handle_new_message_does_not_reassign_thinking_id(self) -> None:
        """handle_new_message must not reassign ThinkingPanel.id (Textual forbids it).

        Uses a real ThinkingPanel with a patched remove() to verify no ValueError
        is raised from attempting to set .id after mount.
        """
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "auto"

        log = MagicMock()

        # Use a real ThinkingPanel to verify no id reassignment occurs
        thinking_panel = ThinkingPanel(sender="codex", id="thinking-codex")
        thinking_panel.thinking_text = "some reasoning"
        thinking_panel.remove = MagicMock()  # Patch remove to avoid NoActiveAppError
        streaming_panel = MagicMock(spec=StreamingPanel)

        def query_side_effect(selector):
            if "thinking-codex" in selector:
                return [thinking_panel]
            if "stream-codex" in selector:
                return [streaming_panel]
            return []

        log.query.side_effect = query_side_effect

        event = NewMessage(sender="codex", body="Final answer", sequence=3)

        # This should NOT raise ValueError from id reassignment
        app.handle_new_message(log, event)

        # Old panel should be removed
        thinking_panel.remove.assert_called_once()
        # Find the mount call for the new ThinkingPanel (not the MessagePanel)
        thinking_mounts = [call for call in log.mount.call_args_list if isinstance(call[0][0], ThinkingPanel)]
        assert len(thinking_mounts) == 1
        new_tp = thinking_mounts[0][0][0]
        assert new_tp.thinking_text == "some reasoning"

    def test_handle_new_message_respects_visibility_hide(self) -> None:
        """If visibility is hide, ThinkingPanel shouldn't exist anyway, but logic holds."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "hide"

        log = MagicMock()
        streaming_panel = MagicMock(spec=StreamingPanel)

        def query_side_effect(selector):
            if "stream-claude" in selector:
                return [streaming_panel]
            return []

        log.query.side_effect = query_side_effect

        # query_one for thinking will fail
        log.query_one.side_effect = Exception("Not found")

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        streaming_panel.remove.assert_called_once()
        # Should mount before streaming panel
        _args, kwargs = log.mount.call_args
        assert kwargs["before"] == streaming_panel

    def test_handle_new_message_respects_visibility_show(self) -> None:
        """If visibility is show, do NOT collapse the new ThinkingPanel."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "show"

        log = MagicMock()
        thinking_panel = MagicMock(spec=ThinkingPanel)
        thinking_panel.thinking_text = "reasoning"
        thinking_panel.start_time = 1000.0
        thinking_panel.user_pinned = False
        thinking_panel.expanded = True
        streaming_panel = MagicMock(spec=StreamingPanel)

        def query_side_effect(selector):
            if "thinking-claude" in selector:
                return [thinking_panel]
            if "stream-claude" in selector:
                return [streaming_panel]
            return []

        log.query.side_effect = query_side_effect

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        # Old panel removed, new one mounted
        thinking_panel.remove.assert_called_once()
        streaming_panel.remove.assert_called_once()
        # New ThinkingPanel should NOT be collapsed (visibility=show)
        thinking_mounts = [call for call in log.mount.call_args_list if isinstance(call[0][0], ThinkingPanel)]
        assert len(thinking_mounts) == 1
        new_tp = thinking_mounts[0][0][0]
        assert new_tp.expanded is True  # Not collapsed
