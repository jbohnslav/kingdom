from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
SMOKE = REPO_ROOT / "scripts" / "smoke.sh"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = REPO_ROOT / ".github" / "workflows" / "release.yml"


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
        "## Deprecated ticket command migrations", 1
    )[0]
    assert optional_design.index("kd design                       # initialize") < optional_design.index(
        "kd design show"
    )


def test_readme_preserves_staged_deprecation_contracts() -> None:
    text = README.read_text()

    assert "`kd tk move` is deprecated and will be removed in v1.0.0" in text
    assert "`kd tk pull`" in text
    assert "`kd tk defer --reason`" in text
    assert "`kd tk add-note` is a hidden compatibility alias that will be removed in v0.8.0" in text
    assert "Use `kd tk log` instead" in text


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
