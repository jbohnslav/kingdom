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
