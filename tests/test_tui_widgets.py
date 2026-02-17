"""Tests for TUI message widgets."""

from __future__ import annotations

import pytest

from kingdom.tui.widgets import (
    ErrorPanel,
    MessagePanel,
    StreamingPanel,
    ThinkingPanel,
    WaitingPanel,
    color_for_member,
    format_elapsed,
)


class TestFormatElapsed:
    """Tests for human-friendly elapsed time formatting."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0.0, "0.0s"),
            (1.5, "1.5s"),
            (12.3, "12.3s"),
            (59.9, "59.9s"),
            (60.0, "1m 0s"),
            (61.0, "1m 1s"),
            (83.2, "1m 23s"),
            (119.9, "1m 59s"),
            (120.0, "2m 0s"),
            (599.0, "9m 59s"),
            (3600.0, "1h 0m 0s"),
            (3661.0, "1h 1m 1s"),
            (7384.0, "2h 3m 4s"),
        ],
    )
    def test_format_elapsed(self, seconds: float, expected: str) -> None:
        assert format_elapsed(seconds) == expected

    def test_sub_second_precision(self) -> None:
        """Values under 60s keep one decimal place."""
        assert format_elapsed(0.1) == "0.1s"
        assert format_elapsed(45.678) == "45.7s"

    def test_minutes_drop_decimals(self) -> None:
        """Values >= 60s use integer seconds (no decimals)."""
        result = format_elapsed(90.9)
        assert result == "1m 30s"  # int(90.9) = 90 -> 1m 30s


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
        from kingdom.tui.widgets import BRAND_MEMBER_COLORS, FALLBACK_COLORS

        all_colors = set(BRAND_MEMBER_COLORS.values()) | set(FALLBACK_COLORS)
        for name in ["claude", "codex", "cursor"]:
            assert color_for_member(name) in all_colors

    def test_claude_gets_brand_orange(self) -> None:
        """Claude should get Anthropic's brand orange, not a generic color."""
        assert color_for_member("claude") == "#d97706"

    def test_codex_gets_openai_green(self) -> None:
        """Codex should get OpenAI's brand green."""
        assert color_for_member("codex") == "#19c37d"

    def test_cursor_gets_brand_blue(self) -> None:
        """Cursor should get a blue accent color."""
        assert color_for_member("cursor") == "dodgerblue"

    def test_brand_colors_are_distinct(self) -> None:
        """All three brand colors must be different from each other."""
        from kingdom.tui.widgets import BRAND_MEMBER_COLORS

        values = list(BRAND_MEMBER_COLORS.values())
        assert len(values) == len(set(values))

    def test_fallback_palette_has_enough_colors(self) -> None:
        """The palette should have enough colors for agent groups."""
        from kingdom.tui.widgets import FALLBACK_COLORS

        assert len(FALLBACK_COLORS) >= 10

    def test_fallback_colors_are_unique(self) -> None:
        """No duplicate entries in the fallback palette."""
        from kingdom.tui.widgets import FALLBACK_COLORS

        assert len(FALLBACK_COLORS) == len(set(FALLBACK_COLORS))

    def test_fallback_avoids_brand_member_colors(self) -> None:
        """Fallback palette should not duplicate the brand member colors."""
        from kingdom.tui.widgets import BRAND_MEMBER_COLORS, FALLBACK_COLORS

        overlap = set(FALLBACK_COLORS) & set(BRAND_MEMBER_COLORS.values())
        assert overlap == set(), f"Overlap with brand member colors: {overlap}"

    def test_unknown_member_uses_fallback(self) -> None:
        """An unknown member name should get a color from the fallback palette."""
        from kingdom.tui.widgets import BRAND_MEMBER_COLORS, FALLBACK_COLORS

        result = color_for_member("mystery_agent")
        assert result not in BRAND_MEMBER_COLORS.values()
        assert result in FALLBACK_COLORS

    def test_many_agents_get_distinct_colors(self) -> None:
        """With 10 unknown agents, most should get distinct colors."""
        names = [f"agent_{i}" for i in range(10)]
        colors = {color_for_member(name) for name in names}
        # With 16 fallback colors, 10 agents should yield at least 6 distinct
        assert len(colors) >= 6


class TestMessagePanel:
    def test_stores_sender_and_body(self) -> None:
        panel = MessagePanel(sender="claude", body="Hello world")
        assert panel.sender == "claude"
        assert panel.body == "Hello world"

    def test_compose_text(self) -> None:
        panel = MessagePanel(sender="codex", body="Analysis here")
        assert panel.compose_text() == "Analysis here"

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


class TestThinkingPanel:
    def test_initial_state(self) -> None:
        panel = ThinkingPanel(sender="cursor")
        assert panel.sender == "cursor"
        assert panel.thinking_text == ""
        assert panel.expanded is True
        assert panel.user_pinned is False

    def test_update_thinking(self) -> None:
        panel = ThinkingPanel(sender="cursor")
        panel.update_thinking("Step 1")
        assert panel.thinking_text == "Step 1"

    def test_collapse(self) -> None:
        panel = ThinkingPanel(sender="cursor")
        panel.update_thinking("Reasoning...")
        panel.collapse()
        assert panel.expanded is False

    def test_collapse_respects_user_pinned(self) -> None:
        panel = ThinkingPanel(sender="cursor")
        panel.user_pinned = True
        panel.expanded = True
        panel.collapse()
        # Should NOT collapse because user pinned it open
        assert panel.expanded is True

    def test_on_click_toggles_and_pins(self) -> None:
        panel = ThinkingPanel(sender="cursor")
        assert panel.expanded is True
        assert panel.user_pinned is False

        panel.on_click()
        assert panel.expanded is False
        assert panel.user_pinned is True

        panel.on_click()
        assert panel.expanded is True
        assert panel.user_pinned is True
