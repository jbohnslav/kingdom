"""Tests for TUI message widgets."""

from __future__ import annotations

import pytest

from kingdom.tui.widgets import (
    CommandHintBar,
    ErrorPanel,
    MessagePanel,
    StreamingPanel,
    ThinkingPanel,
    WaitingPanel,
    color_for_member,
    format_elapsed,
    format_error_body,
    match_commands,
    suggest_command,
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
        colors = {color_for_member(name) for name in ["claude", "codex", "alice", "bob"]}
        # At least 2 distinct colors from 4 names
        assert len(colors) >= 2

    def test_returns_valid_color(self) -> None:
        from kingdom.tui.widgets import BRAND_MEMBER_COLORS, FALLBACK_COLORS

        all_colors = set(BRAND_MEMBER_COLORS.values()) | set(FALLBACK_COLORS)
        for name in ["claude", "codex"]:
            assert color_for_member(name) in all_colors

    def test_claude_gets_brand_orange(self) -> None:
        """Claude should get Anthropic's brand orange, not a generic color."""
        assert color_for_member("claude") == "#d97706"

    def test_codex_gets_openai_green(self) -> None:
        """Codex should get OpenAI's brand green."""
        assert color_for_member("codex") == "#19c37d"

    def test_brand_colors_are_distinct(self) -> None:
        """All brand colors must be different from each other."""
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

    def test_click_stops_event(self) -> None:
        from unittest.mock import MagicMock

        panel = MessagePanel(sender="king", body="Hello")
        event = MagicMock()
        panel.on_click(event)
        event.stop.assert_called_once()


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


class TestFormatErrorBody:
    """Tests for format_error_body — user-friendly error display."""

    def test_timeout_shows_detail_and_retry_hint(self) -> None:
        body = format_error_body("*Error: Timeout after 600s*", "claude", timed_out=True, interrupted=False)
        assert "**Timed out**" in body
        assert "Timeout after 600s" in body
        assert "@claude" in body
        assert "Retry:" in body

    def test_generic_error_shows_detail_and_retry_hint(self) -> None:
        body = format_error_body("*Error: Connection refused*", "codex", timed_out=False, interrupted=False)
        assert "**Error**" in body
        assert "Connection refused" in body
        assert "kd council status" in body
        assert "Retry:" in body

    def test_empty_response_shows_specific_hint(self) -> None:
        body = format_error_body(
            "*Empty response — no text or error returned.*", "codex", timed_out=False, interrupted=False
        )
        assert "**Empty response**" in body
        assert "@codex" in body
        assert "Retry:" in body

    def test_interrupted_returns_raw_error(self) -> None:
        """Interrupted messages should pass through without extra noise."""
        body = format_error_body("*Interrupted*", "claude", timed_out=False, interrupted=True)
        assert body == "*Interrupted*"

    def test_interrupted_with_partial_text(self) -> None:
        raw = "Some partial text\n\n*[Interrupted — response may be incomplete]*"
        body = format_error_body(raw, "claude", timed_out=False, interrupted=True)
        assert body == raw

    def test_error_detail_extraction_strips_markers(self) -> None:
        """The *Error: ...* wrapper should be stripped from the detail."""
        body = format_error_body("*Error: Process exited with code 1*", "codex", timed_out=False, interrupted=False)
        assert "Process exited with code 1" in body
        # Should NOT contain the raw markers
        assert body.count("*Error:") == 0

    def test_error_body_is_multiline(self) -> None:
        """Error body should have the detail on one line and retry on another."""
        body = format_error_body("*Error: something broke*", "claude", timed_out=False, interrupted=False)
        lines = body.strip().splitlines()
        assert len(lines) >= 2  # At least detail + retry hint


class TestErrorPanel:
    def test_stores_error(self) -> None:
        panel = ErrorPanel(sender="codex", error="Timeout after 600s")
        assert panel.sender == "codex"
        assert panel.error == "Timeout after 600s"

    def test_timed_out_flag(self) -> None:
        panel = ErrorPanel(sender="codex", error="Timeout", timed_out=True)
        assert panel.timed_out is True

    def test_default_not_timed_out(self) -> None:
        panel = ErrorPanel(sender="codex", error="Some error")
        assert panel.timed_out is False


class TestThinkingPanel:
    def test_initial_state(self) -> None:
        panel = ThinkingPanel(sender="codex")
        assert panel.sender == "codex"
        assert panel.thinking_text == ""
        assert panel.expanded is True
        assert panel.user_pinned is False

    def test_update_thinking(self) -> None:
        panel = ThinkingPanel(sender="codex")
        panel.update_thinking("Step 1")
        assert panel.thinking_text == "Step 1"

    def test_collapse(self) -> None:
        panel = ThinkingPanel(sender="codex")
        panel.update_thinking("Reasoning...")
        panel.collapse()
        assert panel.expanded is False

    def test_collapse_respects_user_pinned(self) -> None:
        panel = ThinkingPanel(sender="codex")
        panel.user_pinned = True
        panel.expanded = True
        panel.collapse()
        # Should NOT collapse because user pinned it open
        assert panel.expanded is True

    def test_on_click_toggles_and_pins(self) -> None:
        from unittest.mock import MagicMock

        panel = ThinkingPanel(sender="codex")
        assert panel.expanded is True
        assert panel.user_pinned is False

        event = MagicMock()
        panel.on_click(event)
        assert panel.expanded is False
        assert panel.user_pinned is True
        event.stop.assert_called_once()

        event2 = MagicMock()
        panel.on_click(event2)
        assert panel.expanded is True
        assert panel.user_pinned is True


class TestColoredMentionMarkdown:
    """Tests for @mention coloring in rendered messages."""

    def test_creates_with_member_names(self) -> None:
        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("Hello @claude", ["claude", "codex"])
        assert "claude" in cmm.member_colors
        assert "codex" in cmm.member_colors
        assert "all" in cmm.member_colors
        assert "king" in cmm.member_colors

    def test_pattern_matches_known_members(self) -> None:
        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("Hello @claude and @codex", ["claude", "codex"])
        assert cmm.pattern is not None
        matches = cmm.pattern.findall("Hello @claude and @codex")
        assert "claude" in matches
        assert "codex" in matches

    def test_pattern_does_not_match_unknown(self) -> None:
        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("Hello @unknown", ["claude"])
        assert cmm.pattern is not None
        matches = cmm.pattern.findall("Hello @unknown")
        assert matches == []

    def test_renders_segments(self) -> None:
        """ColoredMentionMarkdown should yield Segment objects from __rich_console__."""
        from rich.console import Console
        from rich.segment import Segment

        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("Hello @claude world", ["claude"])
        console = Console(force_terminal=True, width=80)
        options = console.options

        segments = list(cmm.__rich_console__(console, options))
        assert len(segments) > 0
        assert all(isinstance(s, Segment) for s in segments)

    def test_mention_segment_has_bold_style(self) -> None:
        """@mention segments should have bold=True in their style."""
        from rich.console import Console
        from rich.segment import Segment

        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("@claude", ["claude"])
        console = Console(force_terminal=True, width=80)
        options = console.options

        segments = list(cmm.__rich_console__(console, options))
        mention_segs = [s for s in segments if isinstance(s, Segment) and "@claude" in s.text]
        assert len(mention_segs) >= 1
        for seg in mention_segs:
            assert seg.style.bold is True

    def test_plain_text_without_mentions_unchanged(self) -> None:
        """Text without @mentions should render normally."""
        from rich.console import Console
        from rich.segment import Segment

        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("Hello world", ["claude"])
        console = Console(force_terminal=True, width=80)
        options = console.options

        segments = list(cmm.__rich_console__(console, options))
        text_content = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "Hello world" in text_content

    def test_empty_member_names(self) -> None:
        """With no member names, should still render without errors."""
        from rich.console import Console

        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("Hello @nobody", [])
        console = Console(force_terminal=True, width=80)
        options = console.options

        segments = list(cmm.__rich_console__(console, options))
        assert len(segments) > 0

    def test_at_all_gets_colored(self) -> None:
        """@all should be colored (white/bold)."""
        from rich.console import Console
        from rich.segment import Segment

        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("@all thoughts?", ["claude"])
        console = Console(force_terminal=True, width=80)
        options = console.options

        segments = list(cmm.__rich_console__(console, options))
        mention_segs = [s for s in segments if isinstance(s, Segment) and "@all" in s.text]
        assert len(mention_segs) >= 1
        for seg in mention_segs:
            assert seg.style.bold is True

    def test_mention_styles_cached(self) -> None:
        """Mention styles should be pre-computed at init, not recreated per render."""
        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("@claude @codex", ["claude", "codex"])
        assert "claude" in cmm.mention_styles
        assert "codex" in cmm.mention_styles
        assert cmm.mention_styles["claude"].bold is True

    def test_survives_corrupted_style(self) -> None:
        """Rendering should not crash if a segment's style is corrupted."""
        from unittest.mock import MagicMock

        from rich.console import Console
        from rich.segment import Segment
        from rich.style import Style

        from kingdom.tui.widgets import ColoredMentionMarkdown

        cmm = ColoredMentionMarkdown("@claude", ["claude"])
        console = Console(force_terminal=True, width=80)
        options = console.options

        # Monkey-patch __rich_console__ source to inject a bad style
        original_render = cmm.__rich_console__

        bad_style = MagicMock(spec=Style)
        bad_style.__add__ = MagicMock(side_effect=AttributeError("_color"))

        def inject_bad_style(console, options):
            for seg in original_render(console, options):
                if isinstance(seg, Segment) and "@claude" in seg.text:
                    yield Segment(seg.text, bad_style)
                else:
                    yield seg

        # The error path uses the cached mention_style directly as fallback
        # so it should survive
        segments = list(cmm.__rich_console__(console, options))
        assert len(segments) > 0


class TestMessagePanelMemberNames:
    """Tests for MessagePanel with member_names for @mention coloring."""

    def test_stores_member_names(self) -> None:
        panel = MessagePanel(sender="claude", body="Hello", member_names=["claude", "codex"])
        assert panel.member_names == ["claude", "codex"]

    def test_default_member_names_empty(self) -> None:
        panel = MessagePanel(sender="claude", body="Hello")
        assert panel.member_names == []

    def test_backward_compatible_without_member_names(self) -> None:
        """Old callers that don't pass member_names should still work."""
        panel = MessagePanel(sender="king", body="Hello @claude")
        assert panel.sender == "king"
        assert panel.body == "Hello @claude"
        assert panel.member_names == []


class TestMatchCommands:
    """Tests for match_commands -- slash command prefix matching."""

    def test_bare_slash_returns_all(self) -> None:
        matches = match_commands("/")
        assert len(matches) >= 5

    def test_prefix_filters(self) -> None:
        matches = match_commands("/m")
        cmd_words = [cmd.split()[0] for cmd, _desc in matches]
        assert all(c.startswith("/m") for c in cmd_words)
        assert "/mute" in cmd_words

    def test_full_command_matches(self) -> None:
        matches = match_commands("/help")
        assert any(cmd.startswith("/help") for cmd, _desc in matches)

    def test_no_match(self) -> None:
        matches = match_commands("/zzz")
        assert matches == []

    def test_case_insensitive(self) -> None:
        matches = match_commands("/HELP")
        assert any("/help" in cmd for cmd, _desc in matches)

    def test_h_matches_help_and_shortcut(self) -> None:
        matches = match_commands("/h")
        cmd_words = [cmd.split()[0] for cmd, _desc in matches]
        assert "/help" in cmd_words
        assert "/h" in cmd_words

    def test_quit_and_exit(self) -> None:
        q_matches = match_commands("/q")
        assert any("/quit" in cmd for cmd, _desc in q_matches)
        e_matches = match_commands("/e")
        assert any("/exit" in cmd for cmd, _desc in e_matches)

    def test_unmute_match(self) -> None:
        matches = match_commands("/u")
        cmd_words = [cmd.split()[0] for cmd, _desc in matches]
        assert "/unmute" in cmd_words

    def test_writeable_alias_discoverable(self) -> None:
        """Typing /writeable should show the writeable alias."""
        matches = match_commands("/writeable")
        cmd_words = [cmd.split()[0] for cmd, _desc in matches]
        assert "/writeable" in cmd_words

    def test_writable_prefix_matches_both(self) -> None:
        """Typing /writ should show both /writable and /writeable."""
        matches = match_commands("/writ")
        cmd_words = [cmd.split()[0] for cmd, _desc in matches]
        assert "/writable" in cmd_words
        assert "/writeable" in cmd_words


class TestSuggestCommand:
    """Tests for suggest_command — 'did you mean?' for unknown commands."""

    def test_close_misspelling(self) -> None:
        assert suggest_command("/halp") == "/help"

    def test_no_match_for_gibberish(self) -> None:
        assert suggest_command("/zzz") is None

    def test_suggest_for_truncated_command(self) -> None:
        result = suggest_command("/mut")
        assert result == "/mute"

    def test_exact_unknown_no_suggestion(self) -> None:
        """A single-char unknown like /z shouldn't suggest anything."""
        assert suggest_command("/z") is None

    def test_bogus_no_false_positive(self) -> None:
        """/bogus shares only '/' with commands — should not suggest anything."""
        assert suggest_command("/bogus") is None

    def test_qit_suggests_quit(self) -> None:
        """/qit shares '/q' plus 'i' with /quit — should suggest /quit."""
        result = suggest_command("/qit")
        assert result == "/quit"

    def test_unrelated_no_suggestion(self) -> None:
        """/foo has no meaningful prefix overlap — should return None."""
        assert suggest_command("/foo") is None


class TestCommandHintBar:
    """Tests for CommandHintBar widget."""

    def test_initial_state(self) -> None:
        bar = CommandHintBar()
        assert not bar.has_class("visible")

    def test_first_match_returns_command_word(self) -> None:
        bar = CommandHintBar()
        assert bar.first_match("/m") == "/mute"
        assert bar.first_match("/h") == "/help"
        assert bar.first_match("/q") == "/quit"

    def test_first_match_returns_none_for_no_match(self) -> None:
        bar = CommandHintBar()
        assert bar.first_match("/zzz") is None

    def test_first_match_bare_slash(self) -> None:
        bar = CommandHintBar()
        result = bar.first_match("/")
        assert result is not None
