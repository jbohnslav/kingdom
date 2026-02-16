"""Tests for ThinkingPanel persistence in ChatApp."""

from unittest.mock import MagicMock, Mock

from kingdom.tui.app import ChatApp
from kingdom.tui.poll import NewMessage
from kingdom.tui.widgets import MessagePanel, StreamingPanel, ThinkingPanel


class TestThinkingPersistence:
    def test_handle_new_message_preserves_thinking_panel(self) -> None:
        """handle_new_message should not remove ThinkingPanel, but collapse it."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "auto"

        log = MagicMock()

        # Setup existing panels: ThinkingPanel and StreamingPanel
        thinking_panel = MagicMock(spec=ThinkingPanel)
        streaming_panel = MagicMock(spec=StreamingPanel)

        # Mock query results
        def query_side_effect(selector):
            if "thinking-claude" in selector:
                return [thinking_panel]
            if "stream-claude" in selector:
                return [streaming_panel]
            return []

        log.query.side_effect = query_side_effect

        # Mock query_one for finding specific panels
        def query_one_side_effect(selector, type_):
            if "thinking-claude" in selector:
                return thinking_panel
            raise Exception("Not found")

        log.query_one.side_effect = query_one_side_effect

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        # Verify ThinkingPanel was NOT removed
        thinking_panel.remove.assert_not_called()

        # Verify ThinkingPanel was collapsed
        thinking_panel.collapse.assert_called_once()

        # Verify ThinkingPanel was renamed (archived)
        assert thinking_panel.id == "thinking-claude-1"

        # Verify StreamingPanel WAS removed
        streaming_panel.remove.assert_called_once()

        # Verify MessagePanel was mounted before StreamingPanel (which is correct)
        # log.mount(panel, before=existing[0]) where existing[0] is StreamingPanel
        assert log.mount.call_count == 1
        args, kwargs = log.mount.call_args
        assert isinstance(args[0], MessagePanel)
        assert kwargs["before"] == streaming_panel

    def test_handle_new_message_mounts_at_end_if_no_streaming(self) -> None:
        """If only ThinkingPanel exists (no streaming), mount MessagePanel at end."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "auto"

        log = MagicMock()

        thinking_panel = MagicMock(spec=ThinkingPanel)

        # Only ThinkingPanel exists
        def query_side_effect(selector):
            if "thinking-claude" in selector:
                return [thinking_panel]
            return []

        log.query.side_effect = query_side_effect

        def query_one_side_effect(selector, type_):
            if "thinking-claude" in selector:
                return thinking_panel
            raise Exception("Not found")

        log.query_one.side_effect = query_one_side_effect

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        # Verify ThinkingPanel preserved
        thinking_panel.remove.assert_not_called()
        thinking_panel.collapse.assert_called_once()

        # Verify MessagePanel mounted at end (no 'before' arg)
        assert log.mount.call_count == 1
        args, kwargs = log.mount.call_args
        assert isinstance(args[0], MessagePanel)
        assert "before" not in kwargs

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
        """If visibility is show, do NOT collapse ThinkingPanel."""
        app = ChatApp(base=Mock(), branch="main", thread_id="t1")
        app.thinking_visibility = "show"

        log = MagicMock()
        thinking_panel = MagicMock(spec=ThinkingPanel)
        streaming_panel = MagicMock(spec=StreamingPanel)

        def query_side_effect(selector):
            if "thinking-claude" in selector:
                return [thinking_panel]
            if "stream-claude" in selector:
                return [streaming_panel]
            return []

        log.query.side_effect = query_side_effect

        def query_one_side_effect(selector, type_):
            if "thinking-claude" in selector:
                return thinking_panel
            raise Exception("Not found")

        log.query_one.side_effect = query_one_side_effect

        event = NewMessage(sender="claude", body="Final answer", sequence=1)

        app.handle_new_message(log, event)

        thinking_panel.remove.assert_not_called()
        thinking_panel.collapse.assert_not_called()  # Should NOT collapse
        streaming_panel.remove.assert_called_once()
