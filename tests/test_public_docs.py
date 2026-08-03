from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
SMOKE = REPO_ROOT / "scripts" / "smoke.sh"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"
UPGRADING = REPO_ROOT / "docs" / "upgrading.md"
RELEASE_NOTES = REPO_ROOT / "docs" / "releases" / "1.0.0.md"
KINGDOM_SKILL = REPO_ROOT / "skills" / "kingdom" / "SKILL.md"
TICKET_GUIDE = REPO_ROOT / "skills" / "kingdom" / "references" / "tickets.md"


def test_readme_leads_with_ticket_loop_before_power_tools() -> None:
    text = README.read_text()
    core = text.index("## Core ticket loop")
    power_tools = text.index("## Power tools")

    assert core < power_tools
    for command in (
        "kd tk create",
        "kd tk find",
        "kd tk pull",
        "kd tk start",
        "kd tk log",
        "kd tk close",
        "kd tk create --type epic",
        "kd tk create --parent",
    ):
        assert core < text.index(command) < power_tools


def test_worklog_guidance_keeps_command_rich_notes_shell_safe() -> None:
    for path in (README, KINGDOM_SKILL):
        text = path.read_text()
        normalized = " ".join(text.split())

        assert "plain-text-only" in normalized.lower()
        assert "kd tk log <id> <<'WORKLOG'" in text
        assert "direct Markdown" in normalized

    ticket_guidance = " ".join(TICKET_GUIDE.read_text().split())
    assert "plain-text-only" in ticket_guidance.lower()
    assert "stdin or direct Markdown" in ticket_guidance


def test_readme_covers_execution_choices_and_optional_design() -> None:
    text = README.read_text()

    for heading in (
        "## Concurrent agent contexts",
        "### Direct work",
        "### Bounded native subagent",
        "### Reviewed peasant",
        "## Power tools",
        "### Optional design documents",
    ):
        assert heading in text
    assert "owning session" in text
    assert "council review by default" in text
    optional_design = text.split("### Optional design documents", 1)[1].split(
        "## Removed ticket command replacements", 1
    )[0]
    assert optional_design.index("kd design                       # initialize") < optional_design.index(
        "kd design show"
    )


def test_readme_uses_supported_new_council_chat_invocation() -> None:
    text = README.read_text()

    assert "kd council chat                 # create a new thread" in text
    assert "kd council chat --new" not in text


def test_readme_documents_removed_ticket_command_replacements() -> None:
    text = README.read_text()
    replacements = text.split("## Removed ticket command replacements", 1)[1].split("## Ticket closure outcomes", 1)[0]

    assert "`kd tk move` was removed in v1.0.0" in replacements
    assert "`kd tk pull`" in replacements
    assert "`kd tk defer --reason`" in replacements
    assert "`kd tk add-note` was removed in v1.0.0" in replacements
    assert "Use `kd tk log`" in replacements
    assert "will be removed" not in replacements

    ticket_guidance = TICKET_GUIDE.read_text()
    assert "`kd tk move` was removed in v1.0.0" in ticket_guidance
    assert "will be removed in v1.0.0" not in ticket_guidance


def test_release_notes_preserve_workflow_and_explain_changes() -> None:
    text = RELEASE_NOTES.read_text()

    stayed = text.split("## What stayed", 1)[1].split("## What changed", 1)[0]
    for preserved_surface in ("`kd tk pull`", "council chat TUI", "council review by default"):
        assert preserved_surface in stayed

    changed = text.split("## What changed", 1)[1].split("## Upgrade and rollback", 1)[0]
    for change in (
        "Session-scoped current tickets",
        "Typed closure reasons",
        "Optional design",
        "Command consolidation",
    ):
        assert change in changed


def test_release_notes_are_final_without_claiming_publication() -> None:
    text = RELEASE_NOTES.read_text()
    normalized = " ".join(text.split())

    assert "final source-tree notes" in text
    assert "Pre-cut status" not in text
    assert "## Removed compatibility commands" in text
    assert "were removed from the 1.0.0 public CLI" in text
    assert "`kd tk move`" in text
    assert "`kd tk add-note`" in text
    assert "## Artifact validation and publication" in text
    assert "Artifact validation is performed separately" in text
    assert "does not claim that release artifacts were published" in normalized
    for ticket_id in (
        "473d",
        "b507",
        "7e3e",
        "366d",
        "648d",
        "4e2f",
        "14fa",
        "063d",
        "a298",
        "b245",
        "d88b",
        "50df",
        "2d38",
        "bc0c",
        "f240",
        "ff67",
        "0cb0",
        "64a8",
    ):
        assert f"`{ticket_id}`" in text
    assert "## Resolved correctness issues" in text
    assert "Each linked ticket is now closed with reviewed regression evidence" in normalized
    assert "Other backlog enhancements" in text
    assert "64a8.md" not in text
    assert "future transactional migration capability" in text
    assert "optional presentation work" in normalized

    evidence_links = (
        "473d",
        "b507",
        "7e3e",
        "366d",
        "648d",
        "4e2f",
    )
    for ticket_id in evidence_links:
        relative = Path(".kd/branches/codex-workflow-polish/tickets") / f"{ticket_id}.md"
        assert f"](../../{relative})" in text
        assert (REPO_ROOT / relative).exists()

    known_issue_links = {
        "14fa": Path(".kd/branches/codex-workflow-polish/tickets/14fa.md"),
        "063d": Path(".kd/branches/codex-workflow-polish/tickets/063d.md"),
        "a298": Path(".kd/branches/codex-workflow-polish/tickets/a298.md"),
        "b245": Path(".kd/branches/codex-workflow-polish/tickets/b245.md"),
        "d88b": Path(".kd/branches/codex-workflow-polish/tickets/d88b.md"),
        "50df": Path(".kd/branches/codex-workflow-polish/tickets/50df.md"),
        "2d38": Path(".kd/branches/codex-workflow-polish/tickets/2d38.md"),
        "bc0c": Path(".kd/branches/codex-workflow-polish/tickets/bc0c.md"),
        "f240": Path(".kd/branches/codex-workflow-polish/tickets/f240.md"),
        "ff67": Path(".kd/backlog/tickets/ff67.md"),
        "0cb0": Path(".kd/backlog/tickets/0cb0.md"),
    }
    for ticket_id, relative in known_issue_links.items():
        assert f"[`{ticket_id}`](../../{relative})" in text
        assert (REPO_ROOT / relative).exists()


def test_publish_checklist_keeps_local_and_live_done_gates_distinct() -> None:
    text = (REPO_ROOT / "docs" / "publish-checklist.md").read_text()
    normalized = " ".join(text.split())

    assert "isolated repository and reaches a real `kd done`" in text
    assert "final `uv run kd done` on the release branch" in text
    assert "TUI `/status`" in text
    assert "Merging a version bump does not publish" in normalized
    assert "publication is explicitly authorized" in normalized
    assert "Run workflow" in text
    assert "docs/releases/X.Y.Z.md" in text


def test_smoke_executes_practical_documented_ticket_loop() -> None:
    script = SMOKE.read_text()

    assert "kd breakdown" not in script
    assert "env -u HOME" in script
    assert 'KD_SKILL_HOME="$smoke_root/agent-home"' in script
    assert 'KD_CONTEXT="kingdom-smoke"' in script
    assert "UV_CACHE_DIR=" in script
    for command in (
        "tk create --type epic",
        "tk find",
        "tk create --backlog",
        "tk pull",
        "tk start",
        "tk log",
        "tk close",
    ):
        assert command in script
    assert 'tk close "$epic_id"' in script
    assert 'tk list --parent "$epic_id" --closed' in script
    assert '"${kd[@]}" done' in script


def test_ci_and_release_run_documentation_smoke() -> None:
    assert "bash scripts/smoke.sh" in CI.read_text()
    assert "bash scripts/smoke.sh" in RELEASE.read_text()


def test_release_requires_explicit_matching_version() -> None:
    workflow = RELEASE.read_text()
    trigger = workflow.split("on:\n", 1)[1].split("\njobs:", 1)[0]

    assert "workflow_dispatch:" in trigger
    assert "push:" not in trigger
    assert "version:" in trigger
    assert "required: true" in trigger
    assert 'if [ "$RELEASE_REF" != "refs/heads/master" ]; then' in workflow
    assert 'if [ "$requested_version" != "$project_version" ]; then' in workflow
    assert 'release_notes="docs/releases/${project_version}.md"' in workflow
    assert '--notes-file "$release_notes"' in workflow

    ordered_steps = (
        "Validate requested version",
        "Set up uv",
        "Validate documented CLI workflow",
        "Build",
        "Validate artifacts",
        "Create GitHub Release",
        "Publish to PyPI",
    )
    positions = [workflow.index(step) for step in ordered_steps]
    assert positions == sorted(positions)


def test_upgrade_guide_documents_recoverable_lazy_migration() -> None:
    readme = README.read_text()
    guide = UPGRADING.read_text()

    assert "docs/upgrading.md" in readme
    for text in (
        "cp -R .kd ../kd-backup-YYYYMMDD-HHMMSS",
        "kd tk current",
        "kd doctor",
        "mv -n .kd ../kd-after-upgrade",
        "uv tool install --force kingdom-cli==PREVIOUS_VERSION",
    ):
        assert text in guide
    assert "Ticket IDs, unknown frontmatter, Markdown bodies, and Worklogs remain intact" in guide
    assert "neither the upgraded state nor the backup is deleted" in " ".join(guide.split())
    assert "minimum supported repository shape" in guide
    assert "non-empty legacy `.kd/runs/` directory is an intentional hard boundary" in " ".join(guide.split())
