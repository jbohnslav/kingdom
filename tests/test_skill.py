"""Validate the kingdom agent skill against the Agent Skills spec."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "kingdom"
SKILL_MD = SKILL_DIR / "SKILL.md"
PKG_SKILL_DIR = REPO_ROOT / "src" / "kingdom" / "skill"


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


class TestPackagedSkillMirrorsCanonical:
    """Ensure src/kingdom/skill/ mirrors skills/kingdom/ (symlink or identical content)."""

    def test_skill_md_mirrors_canonical(self) -> None:
        """Packaged SKILL.md must be a symlink to, or match content of, canonical copy."""
        pkg = PKG_SKILL_DIR / "SKILL.md"
        canonical = SKILL_DIR / "SKILL.md"
        assert pkg.exists(), f"Packaged SKILL.md not found: {pkg}"
        if pkg.is_symlink():
            assert (
                pkg.resolve() == canonical.resolve()
            ), f"SKILL.md symlink points to {pkg.resolve()}, expected {canonical.resolve()}"
        else:
            assert (
                pkg.read_text() == canonical.read_text()
            ), "Packaged SKILL.md content differs from canonical skills/kingdom/SKILL.md"

    def test_reference_files_mirror_canonical(self) -> None:
        """Every .md in packaged references/ must mirror its canonical counterpart."""
        canonical_refs = SKILL_DIR / "references"
        pkg_refs = PKG_SKILL_DIR / "references"
        canonical_files = sorted(canonical_refs.glob("*.md"))
        assert canonical_files, "No canonical reference .md files found"

        for canonical_file in canonical_files:
            pkg_file = pkg_refs / canonical_file.name
            assert pkg_file.exists(), f"Packaged reference {canonical_file.name} missing from {pkg_refs}"
            if pkg_file.is_symlink():
                assert pkg_file.resolve() == canonical_file.resolve(), (
                    f"{canonical_file.name} symlink points to {pkg_file.resolve()}, "
                    f"expected {canonical_file.resolve()}"
                )
            else:
                assert (
                    pkg_file.read_text() == canonical_file.read_text()
                ), f"Packaged {canonical_file.name} content differs from canonical copy"

    def test_no_extra_packaged_references(self) -> None:
        """Packaged references/ should not have .md files absent from canonical."""
        canonical_refs = SKILL_DIR / "references"
        pkg_refs = PKG_SKILL_DIR / "references"
        canonical_names = {f.name for f in canonical_refs.glob("*.md")}
        for pkg_file in pkg_refs.glob("*.md"):
            assert (
                pkg_file.name in canonical_names
            ), f"Extra packaged reference {pkg_file.name} not in canonical skills/kingdom/references/"
