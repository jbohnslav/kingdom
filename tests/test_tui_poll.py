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
        text = tail_stream_file(path, 0, "claude_code")
        assert text == "Hello"

    def test_reads_from_offset(self, tdir: Path) -> None:
        path = write_stream_line(tdir, "claude", claude_stream_event("Hello"))
        first_size = path.stat().st_size
        write_stream_line(tdir, "claude", claude_stream_event(" world"))
        text = tail_stream_file(path, first_size, "claude_code")
        assert text == " world"

    def test_returns_empty_for_no_data(self, tdir: Path) -> None:
        path = tdir / ".stream-claude.jsonl"
        path.write_text("", encoding="utf-8")
        text = tail_stream_file(path, 0, "claude_code")
        assert text == ""

    def test_returns_empty_for_missing_file(self, tdir: Path) -> None:
        path = tdir / ".stream-missing.jsonl"
        text = tail_stream_file(path, 0, "claude_code")
        assert text == ""

    def test_skips_non_text_events(self, tdir: Path) -> None:
        path = tdir / ".stream-claude.jsonl"
        path.write_text('{"type": "message_start"}\n', encoding="utf-8")
        text = tail_stream_file(path, 0, "claude_code")
        assert text == ""


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

        # Finalized message arrives
        write_message(tdir, 1, "claude", "Hello world (final)")
        events = poller.poll()

        finished = [e for e in events if isinstance(e, StreamFinished)]
        assert len(finished) == 1
        assert finished[0].member == "claude"
        assert "claude" not in poller.active_streams

    def test_finalized_stream_skipped(self, tdir: Path) -> None:
        """After finalization via streaming, stream file updates are ignored."""
        # First: start streaming
        write_stream_line(tdir, "claude", claude_stream_event("partial"))
        poller = ThreadPoller(thread_dir=tdir, member_backends={"claude": "claude_code"})
        poller.poll()
        assert "claude" in poller.active_streams

        # Then: finalized message arrives, stream file still present
        write_message(tdir, 1, "claude", "Final answer")
        write_stream_line(tdir, "claude", claude_stream_event("more stale"))
        events = poller.poll()

        msgs = [e for e in events if isinstance(e, NewMessage)]
        assert len(msgs) == 1
        assert "claude" in poller.finalized_members

        # Further stream updates should be ignored
        write_stream_line(tdir, "claude", claude_stream_event("ignored"))
        events = poller.poll()
        deltas = [e for e in events if isinstance(e, StreamDelta) and e.member == "claude"]
        assert len(deltas) == 0


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


class TestThreadPollerExternalStreams:
    def test_detects_external_stream_file(self, tdir: Path) -> None:
        """Stream files from external processes (kd council ask --async) are detected."""
        write_stream_line(tdir, "codex", '{"type":"item.completed","item":{"type":"agent_message","text":"ext"}}\n')
        poller = ThreadPoller(thread_dir=tdir, member_backends={"codex": "codex"})
        events = poller.poll()

        started = [e for e in events if isinstance(e, StreamStarted)]
        assert len(started) == 1
        assert started[0].member == "codex"
