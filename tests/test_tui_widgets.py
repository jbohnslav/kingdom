"""Tests for TUI message widgets."""

from __future__ import annotations

from kingdom.tui.widgets import (
    ErrorPanel,
    MessagePanel,
    StreamingPanel,
    WaitingPanel,
    color_for_member,
)


class TestColorForMember:
    def test_deterministic(self) -> None:
        """Same name always returns same color."""
        assert color_for_member("claude") == color_for_member("claude")

    def test_different_names_can_differ(self) -> None:
        """Different names should generally produce different colors."""
        colors = {color_for_member(name) for name in ["claude", "codex", "cursor", "alice", "bob"]}
        # At least 2 distinct colors from 5 names
        assert len(colors) >= 2

    def test_returns_valid_color(self) -> None:
        from kingdom.tui.widgets import MEMBER_COLORS

        for name in ["claude", "codex", "cursor"]:
            assert color_for_member(name) in MEMBER_COLORS


class TestMessagePanel:
    def test_stores_sender_and_body(self) -> None:
        panel = MessagePanel(sender="claude", body="Hello world")
        assert panel.sender == "claude"
        assert panel.body == "Hello world"

    def test_compose_text(self) -> None:
        panel = MessagePanel(sender="codex", body="Analysis here")
        assert "**codex**" in panel.compose_text()
        assert "Analysis here" in panel.compose_text()

    def test_king_message(self) -> None:
        panel = MessagePanel(sender="king", body="Question?")
        assert panel.sender == "king"


class TestStreamingPanel:
    def test_initial_state(self) -> None:
        panel = StreamingPanel(sender="claude")
        assert panel.sender == "claude"
        assert panel.content_text == ""

    def test_update_content(self) -> None:
        panel = StreamingPanel(sender="claude")
        panel.update_content("First chunk")
        assert panel.content_text == "First chunk"

    def test_update_content_accumulates(self) -> None:
        panel = StreamingPanel(sender="claude")
        panel.update_content("Hello")
        panel.update_content("Hello world")
        assert panel.content_text == "Hello world"


class TestWaitingPanel:
    def test_stores_sender(self) -> None:
        panel = WaitingPanel(sender="codex")
        assert panel.sender == "codex"


class TestErrorPanel:
    def test_stores_error(self) -> None:
        panel = ErrorPanel(sender="cursor", error="Timeout after 600s")
        assert panel.sender == "cursor"
        assert panel.error == "Timeout after 600s"

    def test_timed_out_flag(self) -> None:
        panel = ErrorPanel(sender="cursor", error="Timeout", timed_out=True)
        assert panel.timed_out is True

    def test_default_not_timed_out(self) -> None:
        panel = ErrorPanel(sender="cursor", error="Some error")
        assert panel.timed_out is False
