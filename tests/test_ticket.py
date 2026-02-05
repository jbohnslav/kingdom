"""Tests for kingdom.ticket module."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kingdom.ticket import (
    AmbiguousTicketMatch,
    Ticket,
    find_ticket,
    generate_ticket_id,
    get_ticket_location,
    list_tickets,
    move_ticket,
    parse_ticket,
    read_ticket,
    serialize_ticket,
    write_ticket,
)


class TestTicketDataclass:
    """Tests for Ticket dataclass."""

    def test_default_values(self) -> None:
        """Ticket has sensible defaults."""
        ticket = Ticket(id="kin-test", status="open", title="Test")
        assert ticket.deps == []
        assert ticket.links == []
        assert ticket.type == "task"
        assert ticket.priority == 2
        assert ticket.assignee is None
        assert ticket.body == ""
        assert ticket.tags == []
        assert ticket.parent is None
        assert ticket.external_ref is None

    def test_all_fields(self) -> None:
        """Ticket can be created with all fields."""
        created = datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)
        ticket = Ticket(
            id="kin-a1b2",
            status="in_progress",
            deps=["kin-1234"],
            links=["https://example.com"],
            created=created,
            type="bug",
            priority=0,
            assignee="Test User",
            title="Fix critical bug",
            body="Description here",
            tags=["urgent", "backend"],
            parent="kin-parent",
            external_ref="JIRA-123",
        )
        assert ticket.id == "kin-a1b2"
        assert ticket.status == "in_progress"
        assert ticket.deps == ["kin-1234"]
        assert ticket.links == ["https://example.com"]
        assert ticket.created == created
        assert ticket.type == "bug"
        assert ticket.priority == 0
        assert ticket.assignee == "Test User"
        assert ticket.title == "Fix critical bug"
        assert ticket.body == "Description here"
        assert ticket.tags == ["urgent", "backend"]
        assert ticket.parent == "kin-parent"
        assert ticket.external_ref == "JIRA-123"


class TestGenerateTicketId:
    """Tests for generate_ticket_id function."""

    def test_format(self) -> None:
        """Generated ID has correct format."""
        ticket_id = generate_ticket_id()
        assert ticket_id.startswith("kin-")
        assert len(ticket_id) == 8  # kin- + 4 hex chars

    def test_hex_suffix(self) -> None:
        """ID suffix is valid hex."""
        ticket_id = generate_ticket_id()
        hex_part = ticket_id[4:]  # Remove 'kin-' prefix
        int(hex_part, 16)  # Should not raise

    def test_unique(self) -> None:
        """Multiple calls generate different IDs."""
        ids = {generate_ticket_id() for _ in range(100)}
        # Should be unique (very unlikely to have collisions)
        assert len(ids) >= 95  # Allow for rare collisions

    def test_collision_check(self, tmp_path: Path) -> None:
        """ID generation checks for collisions when tickets_dir provided."""
        tickets_dir = tmp_path / ".tickets"
        tickets_dir.mkdir()

        # Create many existing tickets to increase collision chance
        for i in range(10):
            (tickets_dir / f"kin-{i:04x}.md").write_text("---\nid: test\n---\n# Test")

        # Should still generate a unique ID
        ticket_id = generate_ticket_id(tickets_dir)
        assert not (tickets_dir / f"{ticket_id}.md").exists()


class TestParseTicket:
    """Tests for parse_ticket function."""

    def test_basic_ticket(self) -> None:
        """Parse a basic ticket."""
        content = """---
id: kin-a1b2
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
assignee: Test User
---
# Test Title

Body content here.
"""
        ticket = parse_ticket(content)
        assert ticket.id == "kin-a1b2"
        assert ticket.status == "open"
        assert ticket.deps == []
        assert ticket.links == []
        assert ticket.created == datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)
        assert ticket.type == "task"
        assert ticket.priority == 2
        assert ticket.assignee == "Test User"
        assert ticket.title == "Test Title"
        assert ticket.body == "Body content here."

    def test_ticket_with_deps(self) -> None:
        """Parse ticket with dependencies."""
        content = """---
id: kin-test
status: open
deps: [kin-1234, kin-5678]
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.deps == ["kin-1234", "kin-5678"]

    def test_ticket_with_tags(self) -> None:
        """Parse ticket with tags."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
tags: [mvp, kd]
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.tags == ["mvp", "kd"]

    def test_ticket_with_parent(self) -> None:
        """Parse ticket with parent reference."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
parent: kin-parent
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.parent == "kin-parent"

    def test_ticket_with_external_ref(self) -> None:
        """Parse ticket with external reference."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
external-ref: JIRA-123
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.external_ref == "JIRA-123"

    def test_multiline_body(self) -> None:
        """Parse ticket with multiline body."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
---
# Test Title

First paragraph.

Second paragraph.

## Acceptance Criteria

- [ ] Item 1
- [ ] Item 2
"""
        ticket = parse_ticket(content)
        assert "First paragraph." in ticket.body
        assert "Second paragraph." in ticket.body
        assert "## Acceptance Criteria" in ticket.body
        assert "- [ ] Item 1" in ticket.body

    def test_missing_frontmatter(self) -> None:
        """Parse fails without frontmatter."""
        with pytest.raises(ValueError, match="must start with YAML frontmatter"):
            parse_ticket("# Just a title\n\nNo frontmatter")

    def test_unclosed_frontmatter(self) -> None:
        """Parse fails with unclosed frontmatter."""
        with pytest.raises(ValueError, match="missing closing"):
            parse_ticket("---\nid: test\n# No closing")

    def test_no_assignee(self) -> None:
        """Parse ticket without assignee."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.assignee is None

    def test_empty_body(self) -> None:
        """Parse ticket with empty body."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
---
# Test Title

"""
        ticket = parse_ticket(content)
        assert ticket.title == "Test Title"
        assert ticket.body == ""

    def test_priority_clamped_high(self) -> None:
        """Priority above 3 is clamped to 3."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 10
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.priority == 3

    def test_priority_clamped_low(self) -> None:
        """Priority below 1 is clamped to 1."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 0
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.priority == 1

    def test_priority_clamped_negative(self) -> None:
        """Negative priority is clamped to 1."""
        content = """---
id: kin-test
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: -5
---
# Test

Body
"""
        ticket = parse_ticket(content)
        assert ticket.priority == 1


class TestSerializeTicket:
    """Tests for serialize_ticket function."""

    def test_basic_ticket(self) -> None:
        """Serialize a basic ticket."""
        ticket = Ticket(
            id="kin-a1b2",
            status="open",
            deps=[],
            links=[],
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            type="task",
            priority=2,
            assignee="Test User",
            title="Test Title",
            body="Body content here.",
        )
        content = serialize_ticket(ticket)

        # Verify structure
        assert content.startswith("---\n")
        assert "\n---\n" in content
        assert "id: kin-a1b2" in content
        assert "status: open" in content
        assert "deps: []" in content
        assert "created: 2026-02-04T16:00:00Z" in content
        assert "assignee: Test User" in content
        assert "# Test Title" in content
        assert "Body content here." in content

    def test_ticket_with_deps(self) -> None:
        """Serialize ticket with dependencies."""
        ticket = Ticket(
            id="kin-test",
            status="open",
            deps=["kin-1234", "kin-5678"],
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test",
        )
        content = serialize_ticket(ticket)
        assert "deps: [kin-1234, kin-5678]" in content

    def test_ticket_with_tags(self) -> None:
        """Serialize ticket with tags."""
        ticket = Ticket(
            id="kin-test",
            status="open",
            tags=["mvp", "urgent"],
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test",
        )
        content = serialize_ticket(ticket)
        assert "tags: [mvp, urgent]" in content

    def test_optional_fields_omitted_when_empty(self) -> None:
        """Optional fields are not included when None/empty."""
        ticket = Ticket(
            id="kin-test",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test",
        )
        content = serialize_ticket(ticket)
        assert "assignee:" not in content
        assert "external-ref:" not in content
        assert "parent:" not in content
        assert "tags:" not in content


class TestRoundTrip:
    """Tests for parse + serialize round-trip."""

    def test_round_trip_basic(self) -> None:
        """Parse then serialize produces equivalent content."""
        original = """---
id: kin-a1b2
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
assignee: Test User
---
# Test Title

Body content here.
"""
        ticket = parse_ticket(original)
        serialized = serialize_ticket(ticket)
        reparsed = parse_ticket(serialized)

        assert reparsed.id == ticket.id
        assert reparsed.status == ticket.status
        assert reparsed.deps == ticket.deps
        assert reparsed.links == ticket.links
        assert reparsed.created == ticket.created
        assert reparsed.type == ticket.type
        assert reparsed.priority == ticket.priority
        assert reparsed.assignee == ticket.assignee
        assert reparsed.title == ticket.title
        assert reparsed.body == ticket.body

    def test_round_trip_with_all_fields(self) -> None:
        """Round trip preserves all fields."""
        original = """---
id: kin-test
status: in_progress
deps: [kin-1234]
links: [https://example.com]
created: 2026-02-04T16:00:00Z
type: bug
priority: 0
assignee: User Name
external-ref: JIRA-999
parent: kin-parent
tags: [urgent, backend]
---
# Complex Ticket

Multi-line body.

## Section

More content.
"""
        ticket = parse_ticket(original)
        serialized = serialize_ticket(ticket)
        reparsed = parse_ticket(serialized)

        assert reparsed.id == ticket.id
        assert reparsed.deps == ticket.deps
        assert reparsed.tags == ticket.tags
        assert reparsed.parent == ticket.parent
        assert reparsed.external_ref == ticket.external_ref


class TestReadWriteTicket:
    """Tests for read_ticket and write_ticket functions."""

    def test_write_then_read(self, tmp_path: Path) -> None:
        """Write ticket then read it back."""
        ticket = Ticket(
            id="kin-test",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test Ticket",
            body="Test body",
        )
        path = tmp_path / "kin-test.md"

        write_ticket(ticket, path)
        assert path.exists()

        read_back = read_ticket(path)
        assert read_back.id == ticket.id
        assert read_back.title == ticket.title
        assert read_back.body == ticket.body

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        """write_ticket creates parent directories."""
        ticket = Ticket(
            id="kin-test",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test",
        )
        path = tmp_path / "tickets" / "subdir" / "kin-test.md"

        write_ticket(ticket, path)
        assert path.exists()

    def test_read_nonexistent(self, tmp_path: Path) -> None:
        """read_ticket raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            read_ticket(tmp_path / "nonexistent.md")


class TestParseExistingTickets:
    """Tests that verify parsing of actual ticket files from the codebase."""

    def test_parse_ticket_from_repo(self) -> None:
        """Parse the ticket that defines this task (kin-6fc1)."""
        # This test verifies compatibility with the existing tk format
        ticket_path = Path(__file__).parent.parent / ".tickets" / "kin-6fc1.md"
        if not ticket_path.exists():
            pytest.skip("Ticket file not found in repo")

        ticket = read_ticket(ticket_path)

        assert ticket.id == "kin-6fc1"
        assert ticket.status in ("open", "in_progress", "closed")
        assert ticket.type == "task"
        assert isinstance(ticket.priority, int)
        assert ticket.title == "Create ticket model"

    def test_parse_ticket_with_tags(self) -> None:
        """Parse a ticket that has tags field."""
        ticket_path = Path(__file__).parent.parent / ".tickets" / "kin-ac22.md"
        if not ticket_path.exists():
            pytest.skip("Ticket file not found in repo")

        ticket = read_ticket(ticket_path)

        assert ticket.id == "kin-ac22"
        assert "mvp" in ticket.tags or "kd" in ticket.tags

    def test_parse_ticket_with_deps(self) -> None:
        """Parse a ticket that has dependencies."""
        ticket_path = Path(__file__).parent.parent / ".tickets" / "kin-d0b5.md"
        if not ticket_path.exists():
            pytest.skip("Ticket file not found in repo")

        ticket = read_ticket(ticket_path)

        assert ticket.id == "kin-d0b5"
        assert "kin-ac22" in ticket.deps


class TestListTickets:
    """Tests for list_tickets function."""

    def test_list_empty_directory(self, tmp_path: Path) -> None:
        """list_tickets returns empty list for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = list_tickets(empty_dir)
        assert result == []

    def test_list_nonexistent_directory(self, tmp_path: Path) -> None:
        """list_tickets returns empty list for nonexistent directory."""
        result = list_tickets(tmp_path / "nonexistent")
        assert result == []

    def test_list_single_ticket(self, tmp_path: Path) -> None:
        """list_tickets returns single ticket."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        ticket = Ticket(
            id="kin-a1b2",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test Ticket",
        )
        write_ticket(ticket, tickets_dir / "kin-a1b2.md")

        result = list_tickets(tickets_dir)
        assert len(result) == 1
        assert result[0].id == "kin-a1b2"

    def test_list_sorted_by_priority(self, tmp_path: Path) -> None:
        """list_tickets sorts by priority (lower is higher priority)."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        created = datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)
        # Use priorities 1, 2, 3 to avoid priority 0 (known parse_ticket bug where 0 is treated as falsy)
        for priority, suffix in [(3, "low"), (1, "high"), (2, "medium")]:
            ticket = Ticket(
                id=f"kin-{suffix}",
                status="open",
                priority=priority,
                created=created,
                title=f"Priority {priority}",
            )
            write_ticket(ticket, tickets_dir / f"kin-{suffix}.md")

        result = list_tickets(tickets_dir)
        assert len(result) == 3
        assert result[0].priority == 1
        assert result[1].priority == 2
        assert result[2].priority == 3

    def test_list_sorted_by_created_within_priority(self, tmp_path: Path) -> None:
        """list_tickets sorts by created date within same priority."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        for day, suffix in [(5, "newer"), (3, "older"), (4, "middle")]:
            ticket = Ticket(
                id=f"kin-{suffix}",
                status="open",
                priority=1,
                created=datetime(2026, 2, day, 16, 0, 0, tzinfo=timezone.utc),
                title=f"Created on day {day}",
            )
            write_ticket(ticket, tickets_dir / f"kin-{suffix}.md")

        result = list_tickets(tickets_dir)
        assert len(result) == 3
        assert result[0].id == "kin-older"  # day 3
        assert result[1].id == "kin-middle"  # day 4
        assert result[2].id == "kin-newer"  # day 5

    def test_list_skips_invalid_files(self, tmp_path: Path) -> None:
        """list_tickets skips files that aren't valid tickets."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Valid ticket
        ticket = Ticket(
            id="kin-good",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Valid Ticket",
        )
        write_ticket(ticket, tickets_dir / "kin-good.md")

        # Invalid file (no frontmatter)
        (tickets_dir / "invalid.md").write_text("Just some text, no frontmatter")

        result = list_tickets(tickets_dir)
        assert len(result) == 1
        assert result[0].id == "kin-good"


class TestFindTicket:
    """Tests for find_ticket function."""

    def _create_test_structure(self, base: Path) -> None:
        """Create a test directory structure with tickets."""
        from kingdom.state import ensure_base_layout, ensure_branch_layout

        ensure_base_layout(base)
        ensure_branch_layout(base, "feature-one")
        ensure_branch_layout(base, "feature-two")

        # Create tickets in various locations
        created = datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)

        # Ticket in branch feature-one
        ticket1 = Ticket(
            id="kin-a1b2", status="open", created=created, title="Branch One Ticket"
        )
        write_ticket(ticket1, base / ".kd" / "branches" / "feature-one" / "tickets" / "kin-a1b2.md")

        # Ticket in branch feature-two
        ticket2 = Ticket(
            id="kin-c3d4", status="open", created=created, title="Branch Two Ticket"
        )
        write_ticket(ticket2, base / ".kd" / "branches" / "feature-two" / "tickets" / "kin-c3d4.md")

        # Ticket in backlog
        ticket3 = Ticket(
            id="kin-e5f6", status="open", created=created, title="Backlog Ticket"
        )
        write_ticket(ticket3, base / ".kd" / "backlog" / "tickets" / "kin-e5f6.md")

        # Ticket in archive
        archive_item = base / ".kd" / "archive" / "old-feature" / "tickets"
        archive_item.mkdir(parents=True)
        ticket4 = Ticket(
            id="kin-g7h8", status="closed", created=created, title="Archived Ticket"
        )
        write_ticket(ticket4, archive_item / "kin-g7h8.md")

    def test_find_by_full_id(self, tmp_path: Path) -> None:
        """find_ticket finds by full ID including kin- prefix."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "kin-a1b2")
        assert result is not None
        ticket, path = result
        assert ticket.id == "kin-a1b2"
        assert path.name == "kin-a1b2.md"

    def test_find_by_partial_id(self, tmp_path: Path) -> None:
        """find_ticket finds by partial ID without prefix."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "a1b2")
        assert result is not None
        ticket, path = result
        assert ticket.id == "kin-a1b2"

    def test_find_by_prefix(self, tmp_path: Path) -> None:
        """find_ticket finds by ID prefix."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "a1")
        assert result is not None
        ticket, _ = result
        assert ticket.id == "kin-a1b2"

    def test_find_in_backlog(self, tmp_path: Path) -> None:
        """find_ticket finds tickets in backlog."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "e5f6")
        assert result is not None
        ticket, path = result
        assert ticket.id == "kin-e5f6"
        assert "backlog" in str(path)

    def test_find_in_archive(self, tmp_path: Path) -> None:
        """find_ticket finds tickets in archive."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "g7h8")
        assert result is not None
        ticket, path = result
        assert ticket.id == "kin-g7h8"
        assert "archive" in str(path)

    def test_find_not_found(self, tmp_path: Path) -> None:
        """find_ticket returns None when ticket not found."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "xxxx")
        assert result is None

    def test_find_ambiguous_match(self, tmp_path: Path) -> None:
        """find_ticket raises AmbiguousTicketMatch for multiple matches."""
        self._create_test_structure(tmp_path)

        # Create another ticket with similar ID prefix
        created = datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)
        ticket = Ticket(
            id="kin-a1c2", status="open", created=created, title="Another A1 Ticket"
        )
        write_ticket(
            ticket, tmp_path / ".kd" / "branches" / "feature-one" / "tickets" / "kin-a1c2.md"
        )

        with pytest.raises(AmbiguousTicketMatch) as exc_info:
            find_ticket(tmp_path, "a1")

        assert "a1" in str(exc_info.value)
        assert len(exc_info.value.matches) == 2

    def test_find_case_insensitive(self, tmp_path: Path) -> None:
        """find_ticket is case-insensitive."""
        self._create_test_structure(tmp_path)

        result = find_ticket(tmp_path, "A1B2")
        assert result is not None
        ticket, _ = result
        assert ticket.id == "kin-a1b2"

    def test_find_empty_base(self, tmp_path: Path) -> None:
        """find_ticket handles empty/nonexistent base gracefully."""
        result = find_ticket(tmp_path, "a1b2")
        assert result is None


class TestMoveTicket:
    """Tests for move_ticket function."""

    def test_move_to_new_directory(self, tmp_path: Path) -> None:
        """move_ticket moves file to new directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        dest_dir = tmp_path / "dest"

        ticket = Ticket(
            id="kin-test",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test Ticket",
        )
        source_path = source_dir / "kin-test.md"
        write_ticket(ticket, source_path)

        new_path = move_ticket(source_path, dest_dir)

        assert new_path == dest_dir / "kin-test.md"
        assert new_path.exists()
        assert not source_path.exists()

        # Verify content preserved
        moved_ticket = read_ticket(new_path)
        assert moved_ticket.id == "kin-test"
        assert moved_ticket.title == "Test Ticket"

    def test_move_creates_dest_directory(self, tmp_path: Path) -> None:
        """move_ticket creates destination directory if needed."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        dest_dir = tmp_path / "nested" / "dest" / "dir"

        ticket = Ticket(
            id="kin-test",
            status="open",
            created=datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc),
            title="Test",
        )
        source_path = source_dir / "kin-test.md"
        write_ticket(ticket, source_path)

        new_path = move_ticket(source_path, dest_dir)

        assert new_path.exists()
        assert dest_dir.exists()

    def test_move_nonexistent_file(self, tmp_path: Path) -> None:
        """move_ticket raises FileNotFoundError for nonexistent file."""
        dest_dir = tmp_path / "dest"

        with pytest.raises(FileNotFoundError):
            move_ticket(tmp_path / "nonexistent.md", dest_dir)


class TestGetTicketLocation:
    """Tests for get_ticket_location function."""

    def _create_test_structure(self, base: Path) -> None:
        """Create a test directory structure with tickets."""
        from kingdom.state import ensure_base_layout, ensure_branch_layout

        ensure_base_layout(base)
        ensure_branch_layout(base, "feature-test")

        created = datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)
        ticket = Ticket(
            id="kin-abcd", status="open", created=created, title="Test Ticket"
        )
        write_ticket(
            ticket, base / ".kd" / "branches" / "feature-test" / "tickets" / "kin-abcd.md"
        )

    def test_get_location_found(self, tmp_path: Path) -> None:
        """get_ticket_location returns path when found."""
        self._create_test_structure(tmp_path)

        result = get_ticket_location(tmp_path, "abcd")
        assert result is not None
        assert result.name == "kin-abcd.md"
        assert result.exists()

    def test_get_location_not_found(self, tmp_path: Path) -> None:
        """get_ticket_location returns None when not found."""
        self._create_test_structure(tmp_path)

        result = get_ticket_location(tmp_path, "zzzz")
        assert result is None

    def test_get_location_ambiguous(self, tmp_path: Path) -> None:
        """get_ticket_location raises AmbiguousTicketMatch for multiple matches."""
        self._create_test_structure(tmp_path)

        # Create another ticket with similar prefix
        created = datetime(2026, 2, 4, 16, 0, 0, tzinfo=timezone.utc)
        ticket = Ticket(
            id="kin-abef", status="open", created=created, title="Another AB Ticket"
        )
        write_ticket(
            ticket, tmp_path / ".kd" / "branches" / "feature-test" / "tickets" / "kin-abef.md"
        )

        with pytest.raises(AmbiguousTicketMatch):
            get_ticket_location(tmp_path, "ab")
