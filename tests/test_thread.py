"""Tests for kingdom.thread module."""

from __future__ import annotations

from pathlib import Path

import pytest

from kingdom.state import ensure_branch_layout
from kingdom.thread import (
    Message,
    ThreadMeta,
    add_message,
    create_thread,
    format_thread_history,
    get_thread,
    list_messages,
    list_threads,
    thread_dir,
    threads_root,
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, "feature/test-branch")
    return tmp_path


BRANCH = "feature/test-branch"


class TestPathHelpers:
    def test_threads_root(self, project: Path) -> None:
        root = threads_root(project, BRANCH)
        assert root == project / ".kd" / "branches" / "feature-test-branch" / "threads"

    def test_thread_dir_normalizes_id(self, project: Path) -> None:
        d = thread_dir(project, BRANCH, "Council/Caching Debate")
        assert d.name == "council-caching-debate"

    def test_thread_dir_idempotent(self, project: Path) -> None:
        d1 = thread_dir(project, BRANCH, "my-thread")
        d2 = thread_dir(project, BRANCH, "My Thread")
        assert d1 == d2


class TestCreateThread:
    def test_creates_directory_and_metadata(self, project: Path) -> None:
        meta = create_thread(project, BRANCH, "council-caching", ["claude", "codex"], "council")

        assert isinstance(meta, ThreadMeta)
        assert meta.id == "council-caching"
        assert meta.members == ["claude", "codex"]
        assert meta.pattern == "council"

        tdir = thread_dir(project, BRANCH, "council-caching")
        assert tdir.is_dir()
        assert (tdir / "thread.json").exists()

    def test_normalizes_thread_id(self, project: Path) -> None:
        meta = create_thread(project, BRANCH, "Council/Caching Debate!", ["claude"], "council")
        assert meta.id == "council-caching-debate"

    def test_duplicate_raises(self, project: Path) -> None:
        create_thread(project, BRANCH, "my-thread", ["claude"], "direct")
        with pytest.raises(FileExistsError):
            create_thread(project, BRANCH, "my-thread", ["claude"], "direct")

    def test_duplicate_via_normalization(self, project: Path) -> None:
        create_thread(project, BRANCH, "My Thread", ["claude"], "direct")
        with pytest.raises(FileExistsError):
            create_thread(project, BRANCH, "my-thread", ["claude"], "direct")


class TestGetThread:
    def test_reads_metadata(self, project: Path) -> None:
        create_thread(project, BRANCH, "test-thread", ["claude", "codex"], "council")
        meta = get_thread(project, BRANCH, "test-thread")

        assert meta.id == "test-thread"
        assert meta.members == ["claude", "codex"]
        assert meta.pattern == "council"

    def test_missing_thread_raises(self, project: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_thread(project, BRANCH, "nonexistent")


class TestListThreads:
    def test_empty(self, project: Path) -> None:
        assert list_threads(project, BRANCH) == []

    def test_returns_all_threads(self, project: Path) -> None:
        create_thread(project, BRANCH, "thread-a", ["claude"], "direct")
        create_thread(project, BRANCH, "thread-b", ["codex"], "council")

        threads = list_threads(project, BRANCH)
        assert len(threads) == 2
        ids = [t.id for t in threads]
        assert "thread-a" in ids
        assert "thread-b" in ids

    def test_ignores_dirs_without_metadata(self, project: Path) -> None:
        create_thread(project, BRANCH, "valid", ["claude"], "direct")
        # Create a stray directory without thread.json
        stray = threads_root(project, BRANCH) / "stray-dir"
        stray.mkdir(parents=True)

        threads = list_threads(project, BRANCH)
        assert len(threads) == 1
        assert threads[0].id == "valid"


class TestAddMessage:
    def test_writes_first_message(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king", "claude"], "direct")
        msg = add_message(project, BRANCH, "test", from_="king", to="claude", body="Hello")

        assert isinstance(msg, Message)
        assert msg.from_ == "king"
        assert msg.to == "claude"
        assert msg.body == "Hello"
        assert msg.sequence == 1

        # File exists with correct name
        tdir = thread_dir(project, BRANCH, "test")
        assert (tdir / "0001-king.md").exists()

    def test_sequential_numbering(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king", "claude"], "direct")

        msg1 = add_message(project, BRANCH, "test", from_="king", to="claude", body="First")
        msg2 = add_message(project, BRANCH, "test", from_="claude", to="king", body="Second")
        msg3 = add_message(project, BRANCH, "test", from_="king", to="all", body="Third")

        assert msg1.sequence == 1
        assert msg2.sequence == 2
        assert msg3.sequence == 3

        tdir = thread_dir(project, BRANCH, "test")
        assert (tdir / "0001-king.md").exists()
        assert (tdir / "0002-claude.md").exists()
        assert (tdir / "0003-king.md").exists()

    def test_message_frontmatter_format(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king", "claude"], "direct")
        add_message(
            project,
            BRANCH,
            "test",
            from_="king",
            to="claude",
            body="Check this out",
            refs=["src/main.py", "tests/test_main.py"],
        )

        tdir = thread_dir(project, BRANCH, "test")
        content = (tdir / "0001-king.md").read_text()

        assert content.startswith("---\n")
        assert "from: king" in content
        assert "to: claude" in content
        assert "timestamp:" in content
        assert "refs:" in content
        assert "src/main.py" in content
        assert "Check this out" in content

    def test_missing_thread_raises(self, project: Path) -> None:
        with pytest.raises(FileNotFoundError):
            add_message(project, BRANCH, "nonexistent", from_="king", to="all", body="Hi")

    def test_sender_name_normalized_in_filename(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["King Claude"], "direct")
        add_message(project, BRANCH, "test", from_="King Claude", to="all", body="Hello")

        tdir = thread_dir(project, BRANCH, "test")
        assert (tdir / "0001-king-claude.md").exists()

    def test_refs_optional(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king"], "direct")
        msg = add_message(project, BRANCH, "test", from_="king", to="all", body="No refs")
        assert msg.refs == []

        tdir = thread_dir(project, BRANCH, "test")
        content = (tdir / "0001-king.md").read_text()
        assert "refs:" not in content


class TestListMessages:
    def test_empty_thread(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king"], "direct")
        assert list_messages(project, BRANCH, "test") == []

    def test_returns_messages_in_order(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "test", from_="king", to="all", body="Question?")
        add_message(project, BRANCH, "test", from_="claude", to="king", body="Answer A")
        add_message(project, BRANCH, "test", from_="codex", to="king", body="Answer B")

        msgs = list_messages(project, BRANCH, "test")
        assert len(msgs) == 3
        assert msgs[0].from_ == "king"
        assert msgs[0].sequence == 1
        assert msgs[1].from_ == "claude"
        assert msgs[1].sequence == 2
        assert msgs[2].from_ == "codex"
        assert msgs[2].sequence == 3

    def test_roundtrip_preserves_content(self, project: Path) -> None:
        create_thread(project, BRANCH, "test", ["king", "claude"], "direct")
        add_message(
            project,
            BRANCH,
            "test",
            from_="king",
            to="claude",
            body="Multi-line\n\nbody with **markdown**",
            refs=["file.py"],
        )

        msgs = list_messages(project, BRANCH, "test")
        assert len(msgs) == 1
        assert msgs[0].body == "Multi-line\n\nbody with **markdown**"
        assert msgs[0].refs == ["file.py"]
        assert msgs[0].from_ == "king"
        assert msgs[0].to == "claude"

    def test_missing_thread_raises(self, project: Path) -> None:
        with pytest.raises(FileNotFoundError):
            list_messages(project, BRANCH, "nonexistent")


class TestEndToEnd:
    def test_council_thread_workflow(self, project: Path) -> None:
        """Simulate a full council discussion thread."""
        # King starts a council thread
        meta = create_thread(
            project,
            BRANCH,
            "council-caching-debate",
            members=["king", "claude", "codex", "cursor"],
            pattern="council",
        )
        assert meta.pattern == "council"

        # King asks a question
        add_message(
            project,
            BRANCH,
            "council-caching-debate",
            from_="king",
            to="all",
            body="Should we use Redis or Memcached?",
            refs=[".kd/branches/feature-test-branch/design.md"],
        )

        # Advisors respond
        add_message(project, BRANCH, "council-caching-debate", from_="claude", to="king", body="Redis for persistence.")
        add_message(
            project, BRANCH, "council-caching-debate", from_="codex", to="king", body="Memcached for simplicity."
        )
        add_message(
            project,
            BRANCH,
            "council-caching-debate",
            from_="cursor",
            to="king",
            body="Redis, it supports more data types.",
        )

        # King follows up with one member
        add_message(
            project, BRANCH, "council-caching-debate", from_="king", to="codex", body="Elaborate on simplicity?"
        )
        add_message(
            project, BRANCH, "council-caching-debate", from_="codex", to="king", body="Less config, no disk I/O."
        )

        # Verify full history
        msgs = list_messages(project, BRANCH, "council-caching-debate")
        assert len(msgs) == 6
        assert [m.sequence for m in msgs] == [1, 2, 3, 4, 5, 6]
        assert msgs[0].from_ == "king"
        assert msgs[4].to == "codex"

        # Verify thread appears in listing
        threads = list_threads(project, BRANCH)
        assert len(threads) == 1
        assert threads[0].id == "council-caching-debate"


class TestFormatThreadHistory:
    """Tests for format_thread_history()."""

    def test_empty_thread(self, project: Path) -> None:
        create_thread(project, BRANCH, "empty", ["king", "claude"], "council")
        tdir = thread_dir(project, BRANCH, "empty")

        result = format_thread_history(tdir, "claude")

        assert result == "---\nYou are claude. Continue the discussion."

    def test_single_message(self, project: Path) -> None:
        create_thread(project, BRANCH, "single", ["king", "claude"], "council")
        add_message(project, BRANCH, "single", from_="king", to="all", body="What do you think?")
        tdir = thread_dir(project, BRANCH, "single")

        result = format_thread_history(tdir, "claude")

        assert "[Previous conversation]" in result
        assert "king: What do you think?" in result
        assert "---\nYou are claude. Continue the discussion." in result

    def test_multi_member_conversation(self, project: Path) -> None:
        create_thread(project, BRANCH, "multi", ["king", "claude", "codex", "cursor"], "council")
        add_message(project, BRANCH, "multi", from_="king", to="all", body="Should we use Redis?")
        add_message(project, BRANCH, "multi", from_="claude", to="king", body="Yes, for persistence.")
        add_message(project, BRANCH, "multi", from_="codex", to="king", body="No, Memcached is simpler.")
        tdir = thread_dir(project, BRANCH, "multi")

        result = format_thread_history(tdir, "cursor")

        assert "king: Should we use Redis?" in result
        assert "claude: Yes, for persistence." in result
        assert "codex: No, Memcached is simpler." in result
        assert "You are cursor. Continue the discussion." in result
        # Messages should appear in sequence order
        king_pos = result.index("king:")
        claude_pos = result.index("claude:")
        codex_pos = result.index("codex:")
        assert king_pos < claude_pos < codex_pos

    def test_directed_messages_included_with_recipient(self, project: Path) -> None:
        create_thread(project, BRANCH, "directed", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "directed", from_="king", to="all", body="General question")
        add_message(project, BRANCH, "directed", from_="king", to="claude", body="Claude, elaborate?")
        add_message(project, BRANCH, "directed", from_="claude", to="king", body="Here's more detail.")
        tdir = thread_dir(project, BRANCH, "directed")

        # codex should see the directed message too (full visibility)
        result = format_thread_history(tdir, "codex")

        assert "king: General question" in result
        assert "king (to claude): Claude, elaborate?" in result
        assert "claude: Here's more detail." in result

    def test_broadcast_messages_no_recipient_annotation(self, project: Path) -> None:
        create_thread(project, BRANCH, "broadcast", ["king", "claude"], "council")
        add_message(project, BRANCH, "broadcast", from_="king", to="all", body="Hello all")
        tdir = thread_dir(project, BRANCH, "broadcast")

        result = format_thread_history(tdir, "claude")

        # Broadcast messages should NOT have "(to all)" annotation
        assert "king: Hello all" in result
        assert "(to all)" not in result

    def test_custom_suffix(self, project: Path) -> None:
        create_thread(project, BRANCH, "suffix", ["king", "claude"], "council")
        add_message(project, BRANCH, "suffix", from_="king", to="all", body="Hi")
        tdir = thread_dir(project, BRANCH, "suffix")

        result = format_thread_history(tdir, "claude", suffix="Respond with a code review.")

        assert result.endswith("---\nRespond with a code review.")

    def test_multiline_body_preserved(self, project: Path) -> None:
        create_thread(project, BRANCH, "multiline", ["king", "claude"], "council")
        add_message(project, BRANCH, "multiline", from_="king", to="all", body="Line one\n\nLine two\n\n## Heading")
        tdir = thread_dir(project, BRANCH, "multiline")

        result = format_thread_history(tdir, "claude")

        assert "Line one\n\nLine two\n\n## Heading" in result


class TestThreadResponseStatus:
    """Tests for thread_response_status() with rich per-member states."""

    def test_all_responded(self, project: Path) -> None:
        from kingdom.thread import (
            MEMBER_RESPONDED,
            thread_response_status,
        )

        create_thread(project, BRANCH, "council-ok", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "council-ok", from_="king", to="all", body="Question")
        add_message(project, BRANCH, "council-ok", from_="claude", to="king", body="Good answer")
        add_message(project, BRANCH, "council-ok", from_="codex", to="king", body="Also good")

        status = thread_response_status(project, BRANCH, "council-ok")

        assert status.responded == {"claude", "codex"}
        assert status.pending == set()
        assert status.member_states["claude"].state == MEMBER_RESPONDED
        assert status.member_states["codex"].state == MEMBER_RESPONDED

    def test_pending_member(self, project: Path) -> None:
        from kingdom.thread import MEMBER_PENDING, MEMBER_RESPONDED, thread_response_status

        create_thread(project, BRANCH, "council-wait", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "council-wait", from_="king", to="all", body="Question")
        add_message(project, BRANCH, "council-wait", from_="claude", to="king", body="My answer")

        status = thread_response_status(project, BRANCH, "council-wait")

        assert status.member_states["claude"].state == MEMBER_RESPONDED
        assert status.member_states["codex"].state == MEMBER_PENDING
        assert "codex" in status.pending

    def test_errored_member(self, project: Path) -> None:
        from kingdom.thread import MEMBER_ERRORED, MEMBER_RESPONDED, thread_response_status

        create_thread(project, BRANCH, "council-err", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "council-err", from_="king", to="all", body="Question")
        add_message(project, BRANCH, "council-err", from_="claude", to="king", body="Good answer")
        add_message(project, BRANCH, "council-err", from_="codex", to="king", body="*Error: Exit code 1*")

        status = thread_response_status(project, BRANCH, "council-err")

        assert status.member_states["claude"].state == MEMBER_RESPONDED
        assert status.member_states["codex"].state == MEMBER_ERRORED
        assert status.member_states["codex"].error is not None
        assert "Exit code" in status.member_states["codex"].error

    def test_timed_out_member(self, project: Path) -> None:
        from kingdom.thread import MEMBER_RESPONDED, MEMBER_TIMED_OUT, thread_response_status

        create_thread(project, BRANCH, "council-to", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "council-to", from_="king", to="all", body="Question")
        add_message(project, BRANCH, "council-to", from_="claude", to="king", body="Good answer")
        add_message(project, BRANCH, "council-to", from_="codex", to="king", body="*Error: Timeout after 600s*")

        status = thread_response_status(project, BRANCH, "council-to")

        assert status.member_states["claude"].state == MEMBER_RESPONDED
        assert status.member_states["codex"].state == MEMBER_TIMED_OUT

    def test_running_member_with_stream_file(self, project: Path) -> None:
        from kingdom.thread import MEMBER_RUNNING, thread_response_status

        create_thread(project, BRANCH, "council-run", ["king", "claude", "codex"], "council")
        add_message(project, BRANCH, "council-run", from_="king", to="all", body="Question")

        # Simulate an active stream file (agent is running)
        tdir = thread_dir(project, BRANCH, "council-run")
        (tdir / ".stream-claude.jsonl").write_text('{"type":"stream_event"}\n')

        status = thread_response_status(project, BRANCH, "council-run")

        assert status.member_states["claude"].state == MEMBER_RUNNING
        assert "claude" in status.pending  # still counted as pending (no message yet)

    def test_empty_response_member(self, project: Path) -> None:
        from kingdom.thread import MEMBER_ERRORED, thread_response_status

        create_thread(project, BRANCH, "council-empty", ["king", "claude"], "council")
        add_message(project, BRANCH, "council-empty", from_="king", to="all", body="Question")
        add_message(
            project,
            BRANCH,
            "council-empty",
            from_="claude",
            to="king",
            body="*Empty response — no text or error returned.*",
        )

        status = thread_response_status(project, BRANCH, "council-empty")

        assert status.member_states["claude"].state == MEMBER_ERRORED
