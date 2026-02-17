"""Tests for TUI file polling logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kingdom.tui.poll import (
    NewMessage,
    StreamDelta,
    StreamFinished,
    StreamStarted,
    ThinkingDelta,
    ThreadPoller,
    read_message_body,
    tail_stream_file,
)


def write_message(tdir: Path, seq: int, sender: str, body: str) -> Path:
    """Write a fake message file to the thread directory."""
    content = f"---\nfrom: {sender}\nto: all\ntimestamp: 2026-01-01T00:00:00Z\n---\n\n{body}\n"
    path = tdir / f"{seq:04d}-{sender}.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_stream_line(tdir: Path, member: str, line: str) -> Path:
    """Append a line to a member's stream file."""
    path = tdir / f".stream-{member}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def claude_stream_event(text: str) -> str:
    """Build a Claude Code stream-json text_delta event."""
    return json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": text},
            },
        }
    )


def cursor_assistant_event(text: str) -> str:
    """Build a Cursor assistant chunk event."""
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": text},
                ],
            },
        }
    )


def cursor_thinking_event(text: str) -> str:
    """Build a Cursor thinking delta event."""
    return json.dumps({"type": "thinking", "subtype": "delta", "text": text})


def codex_text_event(text: str) -> str:
    """Build a Codex agent_message event."""
    return json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}})


def codex_reasoning_event(text: str) -> str:
    """Build a Codex reasoning event."""
    return json.dumps({"type": "item.completed", "item": {"type": "reasoning", "text": text}})


@pytest.fixture()
def tdir(tmp_path: Path) -> Path:
    """Create a thread directory."""
    d = tmp_path / "thread"
    d.mkdir()
    return d


class TestReadMessageBody:
    def test_with_frontmatter(self, tdir: Path) -> None:
        path = write_message(tdir, 1, "king", "Hello world")
        body = read_message_body(path)
        assert body == "Hello world"

    def test_without_frontmatter(self, tdir: Path) -> None:
        path = tdir / "0001-king.md"
        path.write_text("Just plain text\n", encoding="utf-8")
        body = read_message_body(path)
        assert body == "Just plain text"


class TestTailStreamFile:
    def test_reads_new_bytes(self, tdir: Path) -> None:
        path = write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        text, thinking = tail_stream_file(path, 0, "claude_code")
        assert text == "Hello"
        assert thinking == ""

    def test_reads_from_offset(self, tdir: Path) -> None:
        path = write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        first_size = path.stat().st_size
        write_stream_line(tdir, "claude", claude_stream_event(" world"))
        text, thinking = tail_stream_file(path, first_size, "claude_code")
        assert text == " world"
        assert thinking == ""

    def test_returns_empty_for_no_data(self, tdir: Path) -> None:
        path = tdir / ".stream-claude.jsonl"
        path.write_text("", encoding="utf-8")
        text, thinking = tail_stream_file(path, 0, "claude_code")
        assert text == ""
        assert thinking == ""

    def test_returns_empty_for_missing_file(self, tdir: Path) -> None:
        path = tdir / ".stream-missing.jsonl"
        text, thinking = tail_stream_file(path, 0, "claude_code")
        assert text == ""
        assert thinking == ""

    def test_skips_non_text_events(self, tdir: Path) -> None:
        path = tdir / ".stream-claude.jsonl"
        path.write_text('{"type": "message_start"}\n', encoding="utf-8")
        text, thinking = tail_stream_file(path, 0, "claude_code")
        assert text == ""
        assert thinking == ""


class TestThreadPollerMessages:
    def test_detects_new_message(self, tdir: Path) -> None:
        write_message(tdir, 1, "king", "Hello")
        poller = ThreadPoller(thread_dir=tdir)
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(msgs) == 1
        assert msgs[0].sequence == 1
        assert msgs[0].sender == "king"
        assert msgs[0].body == "Hello"

    def test_skips_already_seen_messages(self, tdir: Path) -> None:
        write_message(tdir, 1, "king", "Old")
        poller = ThreadPoller(thread_dir=tdir, last_sequence=1)
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(msgs) == 0

    def test_detects_multiple_new_messages(self, tdir: Path) -> None:
        write_message(tdir, 1, "king", "Q1")
        write_message(tdir, 2, "claude", "A1")
        write_message(tdir, 3, "codex", "A2")
        poller = ThreadPoller(thread_dir=tdir)
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(msgs) == 3
        assert [m.sender for m in msgs] == ["king", "claude", "codex"]

    def test_incremental_detection(self, tdir: Path) -> None:
        write_message(tdir, 1, "king", "Q1")
        poller = ThreadPoller(thread_dir=tdir)
        poller.poll()

        write_message(tdir, 2, "claude", "A1")
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(msgs) == 1
        assert msgs[0].sender == "claude"


class TestThreadPollerStreaming:
    def test_detects_stream_started(self, tdir: Path) -> None:
        write_stream_line(tdir, "claude", claude_stream_event("Hi"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 1
        assert started[0].member == "claude"

    def test_detects_stream_delta(self, tdir: Path) -> None:
        write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == "Hello"

    def test_accumulates_text_across_polls(self, tdir: Path) -> None:
        write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()

        write_stream_line(tdir, "claude", claude_stream_event(" world"))
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == "Hello world"

    def test_no_duplicate_stream_started(self, tdir: Path) -> None:
        write_stream_line(tdir, "claude", claude_stream_event("Hi"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()

        write_stream_line(tdir, "claude", claude_stream_event(" more"))
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 0  # Already started in first poll


class TestThreadPollerFinalization:
    def test_finalization_emits_stream_finished(self, tdir: Path) -> None:
        # Start streaming
        write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()
        assert "claude" in poller.active_streams

        # Simulate run_query: stream file deleted, then finalized message written
        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "claude", "Hello world (final)")
        events = poller.poll()

        finished = [e for e in events if isinstance(e, StreamFinished)]
        assert len(finished) == 1
        assert finished[0].member == "claude"
        assert "claude" not in poller.active_streams

    def test_finalization_clears_stream_state(self, tdir: Path) -> None:
        """After finalization, stream state is cleaned up so round 2 works."""
        # Start streaming
        write_stream_line(tdir, "claude", claude_stream_event("partial"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()
        assert "claude" in poller.active_streams

        # Simulate run_query: stream file deleted, then finalized message written
        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "claude", "Final answer")
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        finished = [e for e in events if isinstance(e, StreamFinished)]
        assert len(msgs) == 1
        assert len(finished) == 1
        assert "claude" not in poller.active_streams
        assert "claude" not in poller.stream_offsets


class TestThreadPollerRetry:
    def test_detects_stream_file_recreation(self, tdir: Path) -> None:
        """If stream file shrinks (retry), reset offset and text."""
        write_stream_line(tdir, "claude", claude_stream_event("First attempt"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()

        old_offset = poller.stream_offsets["claude"]
        assert old_offset > 0

        # Simulate retry: truncate and write new content
        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.write_text(claude_stream_event("Retry") + "\n", encoding="utf-8")
        assert stream_path.stat().st_size < old_offset

        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        # Text should be from retry only, not accumulated from first attempt
        assert deltas[0].full_text == "Retry"


class TestThreadPollerMultiTurn:
    def test_second_round_stream_detected_after_finalization(self, tdir: Path) -> None:
        """After a member is finalized in round 1, a new stream in round 2 must be detected."""
        # Round 1: stream then finalize
        write_stream_line(tdir, "claude", claude_stream_event("Round 1"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()  # picks up stream started + delta

        # Simulate run_query completing: stream file deleted, message file written
        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "king", "Question 1")
        write_message(tdir, 2, "claude", "Answer 1")
        poller.poll()  # picks up finalized messages + stream finished

        assert "claude" not in poller.active_streams

        # Round 2: new king message, new stream appears
        write_message(tdir, 3, "king", "Question 2")
        write_stream_line(tdir, "claude", claude_stream_event("Round 2"))
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(started) == 1, f"Expected StreamStarted for round 2, got {events}"
        assert started[0].member == "claude"
        assert len(deltas) == 1
        assert deltas[0].full_text == "Round 2"


class TestThreadPollerExternalStreams:
    def test_detects_external_stream_file(self, tdir: Path) -> None:
        """Stream files from external processes (kd council ask --async) are detected."""
        write_stream_line(tdir, "codex", '{"type":"item.completed","item":{"type":"agent_message","text":"ext"}}\n')
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 1
        assert started[0].member == "codex"


class TestTailStreamFileThinking:
    def test_no_thinking_for_claude(self, tdir: Path) -> None:
        path = write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        text, thinking = tail_stream_file(path, 0, "claude_code")
        assert text == "Hello"
        assert thinking == ""

    def test_extracts_codex_reasoning(self, tdir: Path) -> None:
        path = write_stream_line(tdir, "codex", codex_reasoning_event("Plan first"))
        text, thinking = tail_stream_file(path, 0, "codex")
        assert text == ""
        assert thinking == "Plan first"


class TestThreadPollerThinking:
    def test_no_thinking_delta_for_claude(self, tdir: Path) -> None:
        """Claude doesn't emit thinking events, so no ThinkingDelta should appear."""
        write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 0

    def test_emits_thinking_delta_for_codex_reasoning(self, tdir: Path) -> None:
        write_stream_line(tdir, "codex", codex_reasoning_event("Reason first"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        assert thinking[0].member == "codex"
        assert thinking[0].full_text == "Reason first"


class TestCodexThinkingNewlines:
    def test_codex_reasoning_blocks_joined_with_newlines(self, tdir: Path) -> None:
        """Multiple Codex reasoning blocks in one batch should be joined with newlines."""
        path = write_stream_line(tdir, "codex", codex_reasoning_event("Step 1"))
        write_stream_line(tdir, "codex", codex_reasoning_event("Step 2"))
        text, thinking = tail_stream_file(path, 0, "codex")
        assert text == ""
        assert thinking == "Step 1\nStep 2"

    def test_codex_reasoning_single_block_no_trailing_newline(self, tdir: Path) -> None:
        """Single reasoning block should not have trailing newline."""
        path = write_stream_line(tdir, "codex", codex_reasoning_event("Only step"))
        _text, thinking = tail_stream_file(path, 0, "codex")
        assert thinking == "Only step"

    def test_codex_reasoning_across_polls_joined_with_newlines(self, tdir: Path) -> None:
        """Codex reasoning blocks arriving in separate poll cycles get newline separators.

        This is the real-world pattern: each item.completed event arrives between
        100ms poll cycles, so tail_stream_file only sees one block per call. The
        cross-batch accumulation in poll_streams must add the newline separator.
        """
        write_stream_line(tdir, "codex", codex_reasoning_event("**Planning retrieval**"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})
        poller.poll()

        write_stream_line(tdir, "codex", codex_reasoning_event("**Inspecting root cause**"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        assert thinking[0].full_text == "**Planning retrieval**\n**Inspecting root cause**"

    def test_codex_reasoning_three_polls_all_separated(self, tdir: Path) -> None:
        """Three reasoning blocks across three polls should have two newline separators."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})

        write_stream_line(tdir, "codex", codex_reasoning_event("Step 1"))
        poller.poll()

        write_stream_line(tdir, "codex", codex_reasoning_event("Step 2"))
        poller.poll()

        write_stream_line(tdir, "codex", codex_reasoning_event("Step 3"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        assert thinking[0].full_text == "Step 1\nStep 2\nStep 3"

    def test_cursor_thinking_across_polls_no_extra_newlines(self, tdir: Path) -> None:
        """Cursor thinking across polls should NOT add extra newline separators.

        Cursor thinking deltas are true deltas (not separate blocks like Codex),
        so they concatenate directly.
        """
        write_stream_line(tdir, "cursor", cursor_thinking_event("Think "))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})
        poller.poll()

        write_stream_line(tdir, "cursor", cursor_thinking_event("more"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        assert thinking[0].full_text == "Think more"


class TestPollerMultiRoundThinking:
    """Tests for thinking behavior across multiple query rounds.

    These simulate the full lifecycle: stream -> finalize -> new stream.
    The bugs we're guarding against:
    - Thinking state leaking from round 1 into round 2
    - Panel ID collisions causing stale panel reuse
    - Newline separators carrying over from a previous round
    """

    def test_codex_thinking_fresh_after_finalization(self, tdir: Path) -> None:
        """After finalization, round 2 thinking starts fresh — no leftover text."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})

        # Round 1: reasoning then finalize
        write_stream_line(tdir, "codex", codex_reasoning_event("Round 1 thinking"))
        poller.poll()
        assert poller.thinking_texts.get("codex") == "Round 1 thinking"

        # Finalize round 1
        stream_path = tdir / ".stream-codex.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "codex", "Round 1 answer")
        poller.poll()
        assert "codex" not in poller.thinking_texts

        # Round 2: fresh thinking
        write_stream_line(tdir, "codex", codex_reasoning_event("Round 2 thinking"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        # Must be ONLY round 2 text, no leftover from round 1
        assert thinking[0].full_text == "Round 2 thinking"

    def test_cursor_thinking_fresh_after_finalization(self, tdir: Path) -> None:
        """Cursor thinking state resets between rounds."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Round 1
        write_stream_line(tdir, "cursor", cursor_thinking_event("Round 1"))
        poller.poll()

        stream_path = tdir / ".stream-cursor.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "cursor", "Answer 1")
        poller.poll()

        # Round 2
        write_stream_line(tdir, "cursor", cursor_thinking_event("Round 2"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        assert thinking[0].full_text == "Round 2"

    def test_codex_multi_round_newlines_dont_leak(self, tdir: Path) -> None:
        """Newline-joined thinking from round 1 should not appear in round 2."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})

        # Round 1: two reasoning blocks
        write_stream_line(tdir, "codex", codex_reasoning_event("R1 step 1"))
        poller.poll()
        write_stream_line(tdir, "codex", codex_reasoning_event("R1 step 2"))
        poller.poll()

        # Finalize
        stream_path = tdir / ".stream-codex.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "codex", "R1 final")
        poller.poll()

        # Round 2: single reasoning block
        write_stream_line(tdir, "codex", codex_reasoning_event("R2 only step"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        # No "R1 step 1\nR1 step 2\n" prefix
        assert thinking[0].full_text == "R2 only step"


class TestPollerStreamBeforeMessage:
    """Tests verifying that poll_streams runs before poll_messages.

    This ordering is critical: if a fast response finishes between poll cycles,
    the stream file may be deleted before the next poll. poll_streams must
    read the last chunk of data before poll_messages processes the finalized
    message and triggers cleanup.
    """

    def test_last_thinking_chunk_captured_before_finalization(self, tdir: Path) -> None:
        """Final thinking data is captured even when message arrives in same poll cycle."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})

        # Stream file with thinking data exists, AND finalized message exists
        # (both written between poll cycles — fast response)
        write_stream_line(tdir, "codex", codex_reasoning_event("Last thought"))
        write_message(tdir, 1, "codex", "Final answer")

        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(thinking) == 1
        assert thinking[0].full_text == "Last thought"
        assert len(msgs) == 1

    def test_last_text_chunk_captured_before_finalization(self, tdir: Path) -> None:
        """Final stream text is captured even when message arrives in same poll cycle."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})

        write_stream_line(tdir, "claude", claude_stream_event("streaming text"))
        write_message(tdir, 1, "claude", "Final answer")

        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(deltas) == 1
        assert deltas[0].full_text == "streaming text"
        assert len(msgs) == 1

    def test_stream_events_come_before_message_events(self, tdir: Path) -> None:
        """In a single poll cycle, stream events should precede message events."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})

        write_stream_line(tdir, "codex", codex_reasoning_event("Thinking"))
        write_message(tdir, 1, "codex", "Done")

        events = poller.poll()

        # Find positions of stream vs message events
        stream_types = (StreamStarted, StreamDelta, ThinkingDelta)
        msg_types = (NewMessage,)
        first_stream_idx = next(i for i, e in enumerate(events) if isinstance(e, stream_types))
        first_msg_idx = next(i for i, e in enumerate(events) if isinstance(e, msg_types))
        assert first_stream_idx < first_msg_idx


class TestPollerCleanupLifecycle:
    """Tests for stream state cleanup when files disappear.

    Guards against "ghost streams" — where stale poller state from a deleted
    stream file causes spurious events on the next round.
    """

    def test_stream_file_disappearance_triggers_cleanup(self, tdir: Path) -> None:
        """When a stream file is deleted, poller clears all associated state."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})

        write_stream_line(tdir, "claude", claude_stream_event("data"))
        poller.poll()
        assert "claude" in poller.active_streams
        assert "claude" in poller.stream_offsets
        assert "claude" in poller.stream_texts

        # Delete stream file (simulating run_query cleanup)
        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.unlink()
        # Also write the message so poll_messages picks it up
        write_message(tdir, 1, "claude", "Final")
        poller.poll()

        assert "claude" not in poller.active_streams
        assert "claude" not in poller.stream_offsets
        assert "claude" not in poller.stream_texts

    def test_thinking_state_cleared_on_file_disappearance(self, tdir: Path) -> None:
        """Thinking text is cleaned up when stream file disappears."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})

        write_stream_line(tdir, "codex", codex_reasoning_event("Thinking"))
        poller.poll()
        assert "codex" in poller.thinking_texts

        stream_path = tdir / ".stream-codex.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "codex", "Answer")
        poller.poll()

        assert "codex" not in poller.thinking_texts

    def test_no_ghost_stream_started_after_cleanup(self, tdir: Path) -> None:
        """After cleanup, a genuinely new stream file triggers StreamStarted — but only once."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})

        # Round 1
        write_stream_line(tdir, "claude", claude_stream_event("R1"))
        poller.poll()

        stream_path = tdir / ".stream-claude.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "claude", "Answer 1")
        poller.poll()  # cleanup happens here

        # Round 2: new stream
        write_stream_line(tdir, "claude", claude_stream_event("R2"))
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 1
        assert started[0].member == "claude"

        # Round 2 continued: no duplicate StreamStarted
        write_stream_line(tdir, "claude", claude_stream_event(" more"))
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 0


class TestCursorSnapshotEdgeCases:
    """Edge cases for Cursor's cumulative snapshot merge logic."""

    def test_three_incremental_snapshots_across_polls(self, tdir: Path) -> None:
        """Three cumulative snapshots across three polls resolve to the final snapshot."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        write_stream_line(tdir, "cursor", cursor_assistant_event("Hello"))
        poller.poll()

        write_stream_line(tdir, "cursor", cursor_assistant_event("Hello world"))
        poller.poll()

        write_stream_line(tdir, "cursor", cursor_assistant_event("Hello world!"))
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == "Hello world!"

    def test_cursor_snapshot_with_thinking_interleaved(self, tdir: Path) -> None:
        """Thinking and text snapshots arriving in same batch both resolve correctly."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Batch 1: thinking
        write_stream_line(tdir, "cursor", cursor_thinking_event("Reasoning..."))
        poller.poll()

        # Batch 2: more thinking + first text snapshot
        write_stream_line(tdir, "cursor", cursor_thinking_event(" more reasoning"))
        write_stream_line(tdir, "cursor", cursor_assistant_event("Answer part 1"))
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(thinking) == 1
        assert thinking[0].full_text == "Reasoning... more reasoning"
        assert len(deltas) == 1
        assert deltas[0].full_text == "Answer part 1"

        # Batch 3: cumulative text snapshot extends
        write_stream_line(tdir, "cursor", cursor_assistant_event("Answer part 1. And part 2."))
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == "Answer part 1. And part 2."

    def test_cursor_snapshot_fresh_after_finalization(self, tdir: Path) -> None:
        """Cursor snapshot state resets between rounds — no bleed from round 1."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Round 1
        write_stream_line(tdir, "cursor", cursor_assistant_event("Round 1 text"))
        poller.poll()

        stream_path = tdir / ".stream-cursor.jsonl"
        stream_path.unlink()
        write_message(tdir, 1, "cursor", "Round 1 final")
        poller.poll()

        # Round 2: different text — must not start with "Round 1 text"
        write_stream_line(tdir, "cursor", cursor_assistant_event("Completely different"))
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == "Completely different"

    def test_cursor_non_cumulative_fragments_concatenated(self, tdir: Path) -> None:
        """Non-overlapping Cursor text fragments are concatenated (not dropped)."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Two within-batch fragments that don't overlap
        write_stream_line(tdir, "cursor", cursor_assistant_event("Part A. "))
        write_stream_line(tdir, "cursor", cursor_assistant_event("Part B."))
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        # Simple concatenation: "Part A. " + "Part B." = "Part A. Part B."
        assert deltas[0].full_text == "Part A. Part B."


class TestPollerEventOrdering:
    """Tests ensuring correct event ordering within a single poll cycle."""

    def test_thinking_before_text_codex(self, tdir: Path) -> None:
        """Codex reasoning event emitted before agent_message in same batch."""
        write_stream_line(tdir, "codex", codex_reasoning_event("Planning"))
        write_stream_line(
            tdir, "codex", json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}})
        )
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})
        events = poller.poll()

        relevant = [e for e in events if isinstance(e, ThinkingDelta | StreamDelta)]
        assert len(relevant) == 2
        assert isinstance(relevant[0], ThinkingDelta)
        assert isinstance(relevant[1], StreamDelta)

    def test_stream_started_before_deltas(self, tdir: Path) -> None:
        """StreamStarted always comes before any ThinkingDelta or StreamDelta."""
        write_stream_line(tdir, "cursor", cursor_thinking_event("Think"))
        write_stream_line(tdir, "cursor", cursor_assistant_event("Text"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})
        events = poller.poll()

        started_idx = next(i for i, e in enumerate(events) if isinstance(e, StreamStarted))
        thinking_idx = next(i for i, e in enumerate(events) if isinstance(e, ThinkingDelta))
        text_idx = next(i for i, e in enumerate(events) if isinstance(e, StreamDelta))
        assert started_idx < thinking_idx < text_idx

    def test_thinking_before_text_across_polls(self, tdir: Path) -> None:
        """When thinking and text arrive in separate polls, ordering is still correct."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Poll 1: only thinking
        write_stream_line(tdir, "cursor", cursor_thinking_event("Reasoning"))
        events1 = poller.poll()
        assert any(isinstance(e, ThinkingDelta) for e in events1)
        assert not any(isinstance(e, StreamDelta) for e in events1)

        # Poll 2: only text
        write_stream_line(tdir, "cursor", cursor_assistant_event("Answer"))
        events2 = poller.poll()
        assert any(isinstance(e, StreamDelta) for e in events2)
        # ThinkingDelta may or may not appear (no new thinking), but StreamDelta must be present


# ---------------------------------------------------------------------------
# Tests based on real Cursor debug stream captures
# Source: .kd/branches/kd-chat/threads/council-72f2/.debug-stream-cursor-*.jsonl
# ---------------------------------------------------------------------------


def cursor_system_init() -> str:
    """Real Cursor system init event from debug stream."""
    return json.dumps(
        {
            "type": "system",
            "subtype": "init",
            "apiKeySource": "login",
            "cwd": "/Users/jrb/code/kingdom",
            "session_id": "12d7149c-3245-439a-8c06-10ad4c9c6020",
            "model": "Gemini 3 Pro",
            "permissionMode": "default",
        }
    )


def cursor_user_event(text: str) -> str:
    """Real Cursor user event from debug stream."""
    return json.dumps(
        {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": text}]},
            "session_id": "12d7149c-3245-439a-8c06-10ad4c9c6020",
        }
    )


def cursor_thinking_completed() -> str:
    """Real Cursor thinking.completed event from debug stream."""
    return json.dumps(
        {
            "type": "thinking",
            "subtype": "completed",
            "session_id": "12d7149c-3245-439a-8c06-10ad4c9c6020",
        }
    )


def cursor_result_event(text: str) -> str:
    """Real Cursor result event from debug stream."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "result": text,
            "session_id": "12d7149c-3245-439a-8c06-10ad4c9c6020",
        }
    )


def cursor_tool_call_event() -> str:
    """Real Cursor tool_call event (thinking is interleaved with these)."""
    return json.dumps(
        {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "0_tool_6f07fe3a",
            "session_id": "12d7149c-3245-439a-8c06-10ad4c9c6020",
        }
    )


class TestRealCursorShortResponse:
    """Tests using real data from debug-stream-cursor-20260216T140757299627Z.jsonl.

    This is the "hi" greeting — fast response (~7.7s total), 2 thinking deltas
    then immediate text. The entire stream completes quickly.
    """

    def test_extraction_from_real_short_stream(self, tdir: Path) -> None:
        """Extractors handle the real Cursor event shapes correctly."""
        path = tdir / ".stream-cursor.jsonl"

        # Write the exact sequence from the debug stream
        lines = [
            cursor_system_init(),
            cursor_user_event("hi"),
            # Two thinking deltas (real text from debug stream)
            json.dumps(
                {
                    "type": "thinking",
                    "subtype": "delta",
                    "text": "**Assessing Initial Conditions**\n\nIdentifying role.\n\n",
                    "session_id": "s1",
                    "timestamp_ms": 1771250874164,
                }
            ),
            json.dumps(
                {
                    "type": "thinking",
                    "subtype": "delta",
                    "text": "**Mapping Out The Response**\n\nDrafting greeting.\n\n",
                    "session_id": "s1",
                    "timestamp_ms": 1771250877008,
                }
            ),
            cursor_thinking_completed(),
            # Fragment assistant events (NOT cumulative), then final snapshot
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "Hello King. Cursor here, ready to assist. What are we working on today",
                            }
                        ],
                    },
                    "session_id": "s1",
                    "timestamp_ms": 1771250877008,
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": "?"}]},
                    "session_id": "s1",
                    "timestamp_ms": 1771250877048,
                }
            ),
            # Final assistant: cumulative snapshot
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "Hello King. Cursor here, ready to assist. What are we working on today?",
                            }
                        ],
                    },
                    "session_id": "s1",
                }
            ),
            cursor_result_event("Hello King. Cursor here, ready to assist. What are we working on today?"),
        ]
        for line in lines:
            with path.open("a") as f:
                f.write(line + "\n")

        text, thinking = tail_stream_file(path, 0, "cursor")

        assert thinking == (
            "**Assessing Initial Conditions**\n\nIdentifying role.\n\n"
            "**Mapping Out The Response**\n\nDrafting greeting.\n\n"
        )
        assert text == "Hello King. Cursor here, ready to assist. What are we working on today?"

    def test_poller_with_real_short_stream_all_at_once(self, tdir: Path) -> None:
        """When entire short Cursor stream arrives in one poll, both thinking and text appear."""
        # Write all events at once (fast response — entire stream lands between polls)
        write_stream_line(tdir, "cursor", cursor_system_init())
        write_stream_line(tdir, "cursor", cursor_user_event("hi"))
        write_stream_line(
            tdir,
            "cursor",
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Assessing**\n\n", "session_id": "s1"}),
        )
        write_stream_line(
            tdir,
            "cursor",
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Planning**\n\n", "session_id": "s1"}),
        )
        write_stream_line(tdir, "cursor", cursor_thinking_completed())
        write_stream_line(
            tdir,
            "cursor",
            cursor_assistant_event("Hello King. Cursor here, ready to assist. What are we working on today?"),
        )
        write_stream_line(
            tdir,
            "cursor",
            cursor_result_event("Hello King. Cursor here, ready to assist. What are we working on today?"),
        )

        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(thinking) == 1, f"Expected ThinkingDelta, got events: {events}"
        assert "**Assessing**" in thinking[0].full_text
        assert "**Planning**" in thinking[0].full_text
        assert len(deltas) == 1
        assert deltas[0].full_text == "Hello King. Cursor here, ready to assist. What are we working on today?"

    def test_poller_thinking_before_text_in_fast_response(self, tdir: Path) -> None:
        """Even when entire stream lands in one poll, ThinkingDelta precedes StreamDelta."""
        write_stream_line(tdir, "cursor", json.dumps({"type": "thinking", "subtype": "delta", "text": "Reasoning"}))
        write_stream_line(tdir, "cursor", cursor_thinking_completed())
        write_stream_line(tdir, "cursor", cursor_assistant_event("Answer"))

        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})
        events = poller.poll()

        relevant = [e for e in events if isinstance(e, ThinkingDelta | StreamDelta)]
        assert len(relevant) == 2
        assert isinstance(relevant[0], ThinkingDelta)
        assert isinstance(relevant[1], StreamDelta)


class TestRealCursorEmptyResponse:
    """Tests based on debug-stream-cursor-20260216T140810200914Z.jsonl.

    This stream has ONLY system init + user message — no thinking, no text.
    Cursor timed out or was interrupted before producing any output.
    """

    def test_no_events_from_empty_cursor_stream(self, tdir: Path) -> None:
        """Stream with only system/user events produces no thinking or text deltas."""
        write_stream_line(tdir, "cursor", cursor_system_init())
        write_stream_line(tdir, "cursor", cursor_user_event("continue discussion"))

        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})
        events = poller.poll()

        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        deltas = [e for e in events if isinstance(e, StreamDelta)]
        # StreamStarted fires (file exists) but no content events
        assert len(thinking) == 0
        assert len(deltas) == 0
        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 1


class TestRealCursorLongResponseWithToolCalls:
    """Tests based on debug-stream-cursor-20260216T140833612805Z.jsonl.

    Long response (~20s) with multiple thinking rounds interleaved with
    tool_call events, followed by assistant text fragments and final snapshot.
    This is the "zen of python" response.
    """

    def test_extraction_with_interleaved_tool_calls(self, tdir: Path) -> None:
        """Thinking extraction works across tool_call boundaries."""
        path = tdir / ".stream-cursor.jsonl"
        lines = [
            cursor_system_init(),
            cursor_user_event("write the zen of python"),
            # Thinking round 1 (before tool call)
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Analyzing the Pythonic Way**\n\n"}),
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Processing the Command Output**\n\n"}),
            cursor_thinking_completed(),
            # Tool call (rejected)
            cursor_tool_call_event(),
            json.dumps({"type": "tool_call", "subtype": "completed", "call_id": "0_tool_6f07fe3a"}),
            # Thinking round 2 (after tool rejection)
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Recalling User's Request**\n\n"}),
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Analyzing Direct Output Strategy**\n\n"}),
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Implementing Direct Output**\n\n"}),
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Considering Prompt's Constraints**\n\n"}),
            cursor_thinking_completed(),
            # Second tool call (also rejected)
            cursor_tool_call_event(),
            json.dumps({"type": "tool_call", "subtype": "completed", "call_id": "0_tool_cc70134b"}),
            # Thinking round 3
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Examining Tool Rejection**\n\n"}),
            json.dumps({"type": "thinking", "subtype": "delta", "text": "**Assessing Output Strategy**\n\n"}),
            cursor_thinking_completed(),
        ]
        for line in lines:
            with path.open("a") as f:
                f.write(line + "\n")

        text, thinking = tail_stream_file(path, 0, "cursor")
        assert text == ""  # No assistant events yet
        assert "**Analyzing the Pythonic Way**" in thinking
        assert "**Recalling User's Request**" in thinking
        assert "**Examining Tool Rejection**" in thinking
        assert "**Assessing Output Strategy**" in thinking

    def test_poller_accumulates_thinking_across_tool_call_rounds(self, tdir: Path) -> None:
        """Thinking from multiple rounds (separated by tool calls) accumulates."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Poll 1: first thinking round
        write_stream_line(tdir, "cursor", cursor_system_init())
        write_stream_line(
            tdir, "cursor", json.dumps({"type": "thinking", "subtype": "delta", "text": "**Round 1 thought**\n\n"})
        )
        write_stream_line(tdir, "cursor", cursor_thinking_completed())
        events1 = poller.poll()
        thinking1 = [e for e in events1 if isinstance(e, ThinkingDelta)]
        assert len(thinking1) == 1
        assert "**Round 1 thought**" in thinking1[0].full_text

        # Poll 2: tool call happens (no extractable content)
        write_stream_line(tdir, "cursor", cursor_tool_call_event())
        write_stream_line(tdir, "cursor", json.dumps({"type": "tool_call", "subtype": "completed", "call_id": "t1"}))
        events2 = poller.poll()
        assert not any(isinstance(e, ThinkingDelta) for e in events2)

        # Poll 3: second thinking round
        write_stream_line(
            tdir, "cursor", json.dumps({"type": "thinking", "subtype": "delta", "text": "**Round 2 thought**\n\n"})
        )
        write_stream_line(tdir, "cursor", cursor_thinking_completed())
        events3 = poller.poll()
        thinking3 = [e for e in events3 if isinstance(e, ThinkingDelta)]
        assert len(thinking3) == 1
        # Both rounds accumulated
        assert "**Round 1 thought**" in thinking3[0].full_text
        assert "**Round 2 thought**" in thinking3[0].full_text

    def test_real_cursor_assistant_fragments_concatenated(self, tdir: Path) -> None:
        """Cursor assistant events are plain fragments concatenated in order.

        From the debug stream: line-by-line fragments like "The Zen of Python, by Tim",
        then " Peters\\n\\nBeautiful is...", concatenated directly.
        """
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Real fragment pattern from debug stream (simplified)
        write_stream_line(tdir, "cursor", cursor_assistant_event("The Zen of Python, by Tim"))
        write_stream_line(tdir, "cursor", cursor_assistant_event(" Peters\n\nBeautiful is better than ugly."))
        write_stream_line(tdir, "cursor", cursor_assistant_event("\nExplicit is better than implicit."))

        events = poller.poll()
        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == (
            "The Zen of Python, by Tim Peters\n\nBeautiful is better than ugly.\nExplicit is better than implicit."
        )

    def test_cursor_fragments_concatenated(self, tdir: Path) -> None:
        """Disjoint Cursor text fragments are concatenated directly."""
        path = tdir / ".stream-cursor.jsonl"
        lines = [
            cursor_assistant_event("Hello King. Cursor here"),
            cursor_assistant_event(", ready to assist."),
            cursor_assistant_event(" What are we working on today?"),
        ]
        for line in lines:
            with path.open("a") as f:
                f.write(line + "\n")

        text, _ = tail_stream_file(path, 0, "cursor")
        assert text == "Hello King. Cursor here, ready to assist. What are we working on today?"

    def test_cursor_cross_batch_fragments(self, tdir: Path) -> None:
        """Fragments across poll batches concatenate correctly."""
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        write_stream_line(tdir, "cursor", cursor_assistant_event("Beautiful is better than ugly."))
        poller.poll()

        write_stream_line(tdir, "cursor", cursor_assistant_event("\nExplicit is better than implicit."))
        events = poller.poll()

        deltas = [e for e in events if isinstance(e, StreamDelta)]
        assert len(deltas) == 1
        assert deltas[0].full_text == ("Beautiful is better than ugly.\nExplicit is better than implicit.")

    def test_cursor_fast_response_stream_persists_for_poll(self, tdir: Path) -> None:
        """Stream file is NOT deleted by run_query, so poller always sees thinking.

        Previously run_query deleted the stream file in its finally block,
        causing a race where fast responses could complete before the poller
        ticked. Now stream files persist until the next session launch.
        """
        poller = ThreadPoller(thread_dir=tdir, member_backends={"cursor": "cursor"})

        # Stream file created and filled — NOT deleted (new behavior)
        write_stream_line(
            tdir, "cursor", json.dumps({"type": "thinking", "subtype": "delta", "text": "**Planning**\n\n"})
        )
        write_stream_line(tdir, "cursor", cursor_assistant_event("Hello!"))

        # Finalized message exists
        write_message(tdir, 1, "cursor", "Hello!")

        events = poller.poll()

        # Thinking is captured because the stream file persists
        thinking = [e for e in events if isinstance(e, ThinkingDelta)]
        assert len(thinking) == 1
        assert "**Planning**" in thinking[0].full_text
