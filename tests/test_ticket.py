"""Tests for kingdom.ticket module."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kingdom.ticket import (
    Ticket,
    generate_ticket_id,
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
