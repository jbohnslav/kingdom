"""Validate the kingdom agent skill against the Agent Skills spec."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "kingdom"
SKILL_MD = SKILL_DIR / "SKILL.md"


def parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a SKILL.md file."""
    text = path.read_text()
    parts = text.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must have YAML frontmatter between --- delimiters"
    return yaml.safe_load(parts[1])


class TestSkillStructure:
    def test_skill_directory_exists(self) -> None:
        assert SKILL_DIR.is_dir(), f"Skill directory not found: {SKILL_DIR}"

    def test_skill_md_exists(self) -> None:
        assert SKILL_MD.is_file(), f"SKILL.md not found: {SKILL_MD}"

    def test_name_matches_parent_directory(self) -> None:
        fm = parse_frontmatter(SKILL_MD)
        assert fm["name"] == SKILL_DIR.name


class TestFrontmatter:
    def test_has_required_fields(self) -> None:
        fm = parse_frontmatter(SKILL_MD)
        assert "name" in fm
        assert "description" in fm

    def test_name_constraints(self) -> None:
        fm = parse_frontmatter(SKILL_MD)
        name = fm["name"]
        assert 1 <= len(name) <= 64
        assert name == name.lower(), "name must be lowercase"
        assert re.fullmatch(
            r"[a-z0-9]+(-[a-z0-9]+)*", name
        ), f"name must be lowercase alphanumeric with single hyphens: {name}"

    def test_description_constraints(self) -> None:
        fm = parse_frontmatter(SKILL_MD)
        desc = fm["description"]
        assert isinstance(desc, str)
        assert 1 <= len(desc) <= 1024, f"description length {len(desc)} outside 1-1024"

    def test_compatibility_constraints(self) -> None:
        fm = parse_frontmatter(SKILL_MD)
        compat = fm.get("compatibility")
        if compat is not None:
            assert len(compat) <= 500, f"compatibility length {len(compat)} exceeds 500"


class TestBody:
    def test_under_500_lines(self) -> None:
        lines = SKILL_MD.read_text().splitlines()
        assert len(lines) <= 500, f"SKILL.md is {len(lines)} lines (max 500)"

    def test_has_body_content(self) -> None:
        text = SKILL_MD.read_text()
        parts = text.split("---", 2)
        body = parts[2].strip()
        assert len(body) > 0, "SKILL.md body is empty"


class TestReferences:
    def test_references_directory_exists(self) -> None:
        refs_dir = SKILL_DIR / "references"
        assert refs_dir.is_dir(), f"references/ directory not found: {refs_dir}"

    def test_reference_links_resolve(self) -> None:
        """Every reference link in SKILL.md must point to an existing file."""
        text = SKILL_MD.read_text()
        # Match markdown links like [text](references/foo.md)
        links = re.findall(r"\]\((references/[^)]+)\)", text)
        assert len(links) > 0, "No reference links found in SKILL.md"
        for link in links:
            path = SKILL_DIR / link
            assert path.is_file(), f"Reference link target missing: {link}"

    def test_no_orphan_references(self) -> None:
        """Every file in references/ must be linked from SKILL.md."""
        text = SKILL_MD.read_text()
        refs_dir = SKILL_DIR / "references"
        for ref_file in sorted(refs_dir.glob("*.md")):
            rel = f"references/{ref_file.name}"
            assert rel in text, f"Orphan reference file not linked from SKILL.md: {rel}"
