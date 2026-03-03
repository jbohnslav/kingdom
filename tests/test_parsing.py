"""Tests for kingdom.parsing module."""

from __future__ import annotations

import pytest

try:
    from kingdom.parsing import (
        parse_frontmatter,
        parse_iso_datetime,
        parse_yaml_value,
        serialize_frontmatter,
        serialize_yaml_value,
    )
except ImportError:
    # When run from the parent worktree's venv, kingdom.parsing may not
    # exist yet.  Skip the entire module in that case.
    pytest.skip("kingdom.parsing not available in this environment", allow_module_level=True)


class TestParseIsoDatetime:
    """Tests for parse_iso_datetime."""

    def test_trailing_z(self) -> None:
        dt = parse_iso_datetime("2026-02-04T16:00:00Z")
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 4
        assert dt.hour == 16
        assert dt.tzinfo is not None

    def test_explicit_offset(self) -> None:
        dt = parse_iso_datetime("2026-02-04T16:00:00+00:00")
        assert dt.year == 2026

    def test_non_utc_offset(self) -> None:
        dt = parse_iso_datetime("2026-02-04T16:00:00-05:00")
        assert dt.hour == 16

    def test_no_timezone(self) -> None:
        dt = parse_iso_datetime("2026-02-04T16:00:00")
        assert dt.tzinfo is None

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_iso_datetime("not-a-date")


class TestParseYamlValue:
    """Tests for parse_yaml_value."""

    def test_empty_string(self) -> None:
        assert parse_yaml_value("") is None

    def test_null_literal(self) -> None:
        assert parse_yaml_value("null") is None
        assert parse_yaml_value("NULL") is None
        assert parse_yaml_value("Null") is None

    def test_tilde_null(self) -> None:
        assert parse_yaml_value("~") is None

    def test_whitespace_only(self) -> None:
        assert parse_yaml_value("   ") is None

    def test_integer(self) -> None:
        assert parse_yaml_value("42") == 42

    def test_negative_integer(self) -> None:
        assert parse_yaml_value("-3") == -3

    def test_zero(self) -> None:
        assert parse_yaml_value("0") == 0

    def test_plain_string(self) -> None:
        assert parse_yaml_value("hello world") == "hello world"

    def test_double_quoted_string(self) -> None:
        assert parse_yaml_value('"hello"') == "hello"

    def test_single_quoted_string(self) -> None:
        assert parse_yaml_value("'hello'") == "hello"

    def test_empty_list(self) -> None:
        assert parse_yaml_value("[]") == []

    def test_list_with_items(self) -> None:
        assert parse_yaml_value("[a, b, c]") == ["a", "b", "c"]

    def test_list_with_quoted_items(self) -> None:
        assert parse_yaml_value('["one", "two"]') == ["one", "two"]

    def test_strips_whitespace(self) -> None:
        assert parse_yaml_value("  hello  ") == "hello"

    def test_string_that_looks_numeric_but_isnt(self) -> None:
        assert parse_yaml_value("12abc") == "12abc"


class TestSerializeFrontmatter:
    """Tests for serialize_frontmatter."""

    def test_basic(self) -> None:
        result = serialize_frontmatter([("status", "open"), ("priority", 2)])
        assert result == "---\nstatus: open\npriority: 2\n---"

    def test_skips_none(self) -> None:
        result = serialize_frontmatter([("status", "open"), ("assignee", None), ("type", "task")])
        assert "assignee" not in result
        assert "status: open" in result
        assert "type: task" in result

    def test_empty_fields(self) -> None:
        result = serialize_frontmatter([])
        assert result == "---\n---"

    def test_list_value(self) -> None:
        result = serialize_frontmatter([("deps", ["a", "b"])])
        assert "deps: [a, b]" in result

    def test_roundtrip(self) -> None:
        """Frontmatter produced by serialize_frontmatter can be parsed back."""
        fm_str = serialize_frontmatter([("id", '"abc"'), ("status", "open"), ("priority", 2)])
        fm, body = parse_frontmatter(fm_str + "\nBody")
        assert fm["id"] == "abc"
        assert fm["status"] == "open"
        assert fm["priority"] == 2
        assert body == "Body"


class TestSerializeYamlValue:
    """Tests for serialize_yaml_value."""

    def test_none(self) -> None:
        assert serialize_yaml_value(None) == ""

    def test_integer(self) -> None:
        assert serialize_yaml_value(42) == "42"

    def test_string(self) -> None:
        assert serialize_yaml_value("hello") == "hello"

    def test_empty_list(self) -> None:
        assert serialize_yaml_value([]) == "[]"

    def test_list(self) -> None:
        assert serialize_yaml_value(["a", "b"]) == "[a, b]"

    def test_bool_true(self) -> None:
        assert serialize_yaml_value(True) == "true"  # type: ignore[arg-type]

    def test_bool_false(self) -> None:
        assert serialize_yaml_value(False) == "false"  # type: ignore[arg-type]


class TestParseFrontmatter:
    """Tests for parse_frontmatter."""

    def test_basic_frontmatter(self) -> None:
        content = "---\nkey: value\n---\nBody text"
        fm, body = parse_frontmatter(content)
        assert fm == {"key": "value"}
        assert body == "Body text"

    def test_multiple_fields(self) -> None:
        content = "---\nid: kin-1234\nstatus: open\npriority: 1\n---\n# Title\n\nBody"
        fm, body = parse_frontmatter(content)
        assert fm["id"] == "kin-1234"
        assert fm["status"] == "open"
        assert fm["priority"] == 1
        assert body == "# Title\n\nBody"

    def test_empty_body(self) -> None:
        content = "---\nkey: value\n---\n"
        fm, body = parse_frontmatter(content)
        assert fm == {"key": "value"}
        assert body == ""

    def test_empty_frontmatter(self) -> None:
        content = "---\n---\nBody"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == "Body"

    def test_missing_opening_delimiter(self) -> None:
        with pytest.raises(ValueError, match="must start with YAML frontmatter"):
            parse_frontmatter("no frontmatter here")

    def test_missing_closing_delimiter(self) -> None:
        with pytest.raises(ValueError, match="missing closing"):
            parse_frontmatter("---\nkey: value\n")

    def test_value_with_colon(self) -> None:
        """Values containing colons (e.g. URLs, timestamps) should be preserved."""
        content = "---\nurl: https://example.com:8080/path\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["url"] == "https://example.com:8080/path"

    def test_timestamp_value(self) -> None:
        """ISO timestamps with colons should be preserved."""
        content = "---\ncreated: 2026-02-04T16:00:00Z\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["created"] == "2026-02-04T16:00:00Z"

    def test_list_value(self) -> None:
        content = "---\ndeps: [kin-0001, kin-0002]\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["deps"] == ["kin-0001", "kin-0002"]

    def test_empty_list_value(self) -> None:
        content = "---\ndeps: []\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["deps"] == []

    def test_null_value(self) -> None:
        content = "---\nassignee: null\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["assignee"] is None

    def test_empty_value(self) -> None:
        content = "---\nassignee:\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["assignee"] is None

    def test_blank_lines_in_frontmatter(self) -> None:
        """Blank lines in frontmatter should be skipped."""
        content = "---\nkey1: val1\n\nkey2: val2\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm == {"key1": "val1", "key2": "val2"}

    def test_whitespace_around_key(self) -> None:
        content = "---\n  key  : value\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["key"] == "value"

    def test_body_with_triple_dashes(self) -> None:
        """Triple dashes in the body should not affect parsing.

        The split("---", 2) limits to 2 splits, so only the first two
        ``---`` are treated as delimiters.
        """
        content = "---\nkey: val\n---\nBody\n---\nMore body"
        fm, body = parse_frontmatter(content)
        assert fm == {"key": "val"}
        assert body == "Body\n---\nMore body"

    def test_body_stripped(self) -> None:
        content = "---\nkey: val\n---\n\n  Body text  \n\n"
        _, body = parse_frontmatter(content)
        assert body == "Body text"

    def test_integer_value(self) -> None:
        content = "---\npriority: 2\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm["priority"] == 2
        assert isinstance(fm["priority"], int)

    def test_line_without_colon_skipped(self) -> None:
        """Lines without colons in frontmatter are silently ignored."""
        content = "---\nkey: val\njust a line\n---\n"
        fm, _ = parse_frontmatter(content)
        assert fm == {"key": "val"}

    def test_only_opening_delimiter(self) -> None:
        """A single --- with no closing should raise ValueError."""
        with pytest.raises(ValueError):
            parse_frontmatter("---\nkey: value")

    def test_quoted_value(self) -> None:
        content = '---\nname: "John Doe"\n---\n'
        fm, _ = parse_frontmatter(content)
        assert fm["name"] == "John Doe"
