"""File polling logic for stream files and finalized messages.

ThreadPoller scans a thread directory for changes on each poll cycle.
Designed for Textual's async loop (called every 100ms via set_interval).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kingdom.agent import extract_stream_text, extract_stream_thinking

# ---------------------------------------------------------------------------
# Poll events
# ---------------------------------------------------------------------------


@dataclass
class NewMessage:
    """A finalized message file was found."""

    sequence: int
    sender: str
    body: str


@dataclass
class StreamStarted:
    """A stream file appeared for a member (new query in progress)."""

    member: str


@dataclass
class StreamDelta:
    """New text extracted from a member's stream file."""

    member: str
    full_text: str  # accumulated text so far


@dataclass
class ThinkingDelta:
    """New thinking/reasoning text extracted from a member's stream file."""

    member: str
    full_text: str  # accumulated thinking text so far


@dataclass
class StreamFinished:
    """A stream finished (finalized message exists for this member)."""

    member: str


PollEvent = NewMessage | StreamStarted | StreamDelta | ThinkingDelta | StreamFinished


# ---------------------------------------------------------------------------
# ThreadPoller
# ---------------------------------------------------------------------------


@dataclass
class ThreadPoller:
    """Polls a thread directory for new messages and streaming updates.

    Attributes:
        thread_dir: Path to the thread directory.
        member_backends: Mapping of member name to backend (for NDJSON extraction).
        last_sequence: Highest seen message sequence number.
        stream_offsets: Byte offset per member stream file.
        stream_texts: Accumulated extracted text per member.
        active_streams: Members whose stream files we are currently tracking.
    """

    thread_dir: Path
    member_backends: dict[str, str] = field(default_factory=dict)
    last_sequence: int = 0
    stream_offsets: dict[str, int] = field(default_factory=dict)
    stream_texts: dict[str, str] = field(default_factory=dict)
    thinking_texts: dict[str, str] = field(default_factory=dict)
    active_streams: set[str] = field(default_factory=set)

    def poll(self) -> list[PollEvent]:
        """Run one poll cycle. Returns a list of events (may be empty)."""
        events: list[PollEvent] = []
        events.extend(self.poll_messages())
        events.extend(self.poll_streams())
        return events

    def poll_messages(self) -> list[PollEvent]:
        """Check for new finalized message files."""
        events: list[PollEvent] = []

        for path in sorted(self.thread_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
            stem = path.stem  # e.g. "0003-claude"
            try:
                seq = int(stem.split("-", 1)[0])
            except (ValueError, IndexError):
                continue

            if seq <= self.last_sequence:
                continue

            # Parse sender from filename
            parts = stem.split("-", 1)
            sender = parts[1] if len(parts) > 1 else "unknown"

            # Read body (skip frontmatter)
            body = read_message_body(path)

            events.append(NewMessage(sequence=seq, sender=sender, body=body))
            self.last_sequence = seq

            # If this member was streaming, mark as finished
            if sender in self.active_streams:
                events.append(StreamFinished(member=sender))
                self.active_streams.discard(sender)
                self.stream_offsets.pop(sender, None)
                self.stream_texts.pop(sender, None)
                self.thinking_texts.pop(sender, None)

        return events

    def poll_streams(self) -> list[PollEvent]:
        """Check for new data in stream files."""
        events: list[PollEvent] = []

        for path in self.thread_dir.glob(".stream-*.jsonl"):
            # Parse member name from filename: .stream-claude.jsonl -> claude
            member = path.name.removeprefix(".stream-").removesuffix(".jsonl")

            try:
                file_size = path.stat().st_size
            except FileNotFoundError:
                continue

            current_offset = self.stream_offsets.get(member, 0)

            # Detect file recreation (retry): file smaller than our offset
            if file_size < current_offset:
                current_offset = 0
                self.stream_texts[member] = ""
                self.thinking_texts[member] = ""

            # New stream file
            if member not in self.active_streams:
                self.active_streams.add(member)
                events.append(StreamStarted(member=member))

            # Read new bytes
            if file_size > current_offset:
                backend = self.member_backends.get(member, "claude_code")
                new_text, new_thinking = tail_stream_file(path, current_offset, backend)
                if new_text:
                    accumulated = self.stream_texts.get(member, "") + new_text
                    self.stream_texts[member] = accumulated
                    events.append(StreamDelta(member=member, full_text=accumulated))
                if new_thinking:
                    accumulated_thinking = self.thinking_texts.get(member, "") + new_thinking
                    self.thinking_texts[member] = accumulated_thinking
                    events.append(ThinkingDelta(member=member, full_text=accumulated_thinking))

                self.stream_offsets[member] = file_size

        return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def read_message_body(path: Path) -> str:
    """Read a message file and return the body (after YAML frontmatter)."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        # Find closing ---
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :].strip()
    return text.strip()


def tail_stream_file(path: Path, offset: int, backend: str) -> tuple[str, str]:
    """Read new bytes from a stream file and extract text and thinking deltas.

    Returns a (text, thinking) tuple of extracted content.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            f.seek(offset)
            new_data = f.read()
    except (FileNotFoundError, OSError):
        return "", ""

    if not new_data:
        return "", ""

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for line in new_data.splitlines():
        line = line.strip()
        if not line:
            continue
        extracted = extract_stream_text(line, backend)
        if extracted:
            text_parts.append(extracted)
        thinking = extract_stream_thinking(line, backend)
        if thinking:
            thinking_parts.append(thinking)

    return "".join(text_parts), "".join(thinking_parts)
