"""Release and CI policies that should survive documentation and version changes."""

import shlex
from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
# BaseLoader keeps GitHub's `on` key as a string rather than a YAML 1.1 boolean.
CI = yaml.load((WORKFLOW_DIR / "ci.yml").read_text(), Loader=yaml.BaseLoader)
RELEASE = yaml.load((WORKFLOW_DIR / "release.yml").read_text(), Loader=yaml.BaseLoader)


def test_release_triggers_on_version_file_changes_with_manual_recovery() -> None:
    triggers = RELEASE["on"]
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"branches": ["master"], "paths": ["pyproject.toml"]}
    version_input = triggers["workflow_dispatch"]["inputs"]["version"]
    assert version_input["required"] == "true"
    assert version_input["type"] == "string"


def test_release_requires_preparation_and_serializes_publication() -> None:
    release = RELEASE["jobs"]["release"]
    assert release["needs"] == "prepare"
    assert release["if"] == "needs.prepare.outputs.publish == 'true'"
    assert release["concurrency"] == {
        "group": "release-${{ needs.prepare.outputs.version }}",
        "cancel-in-progress": "false",
    }


def test_release_validates_before_publication() -> None:
    steps = RELEASE["jobs"]["release"]["steps"]
    required_order = (
        "Run pre-commit",
        "Run tests",
        "Validate documented CLI workflow",
        "Build",
        "Validate artifacts",
        "Create GitHub Release",
        "Publish to PyPI",
    )
    names = [step.get("name") for step in steps]
    positions = [names.index(name) for name in required_order]
    assert positions == sorted(positions)
    for position in positions:
        assert steps[position].get("continue-on-error", "false") == "false"
        assert "if" not in steps[position]


@pytest.mark.parametrize("workflow, job", [(CI, "check"), (RELEASE, "release")], ids=["ci", "release"])
def test_validation_runs_textual_and_cli_smoke(workflow: dict, job: str) -> None:
    steps = {step.get("name"): step for step in workflow["jobs"][job]["steps"]}
    test_command = shlex.split(steps["Run tests"]["run"])
    assert test_command[:3] == ["uv", "run", "pytest"]
    assert "--run-textual-integration" in test_command
    assert shlex.split(steps["Validate documented CLI workflow"]["run"]) == ["bash", "scripts/smoke.sh"]
