import re
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_uv_and_pre_commit_pin_the_same_ruff_version() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    ruff_dependency = next(
        dependency for dependency in pyproject["dependency-groups"]["dev"] if dependency.startswith("ruff")
    )
    assert ruff_dependency.startswith("ruff==")
    uv_version = ruff_dependency.removeprefix("ruff==")

    pre_commit = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text())
    ruff_repo = next(
        repo for repo in pre_commit["repos"] if repo["repo"] == "https://github.com/astral-sh/ruff-pre-commit"
    )
    assert ruff_repo["rev"] == f"v{uv_version}"


def test_project_and_lock_agree_on_version_and_direct_click_dependency() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text())
    package = next(package for package in lock["package"] if package["name"] == project["name"])

    assert package["version"] == project["version"]
    assert any(re.match(r"click(?:[<>=!~;\s]|$)", dependency) for dependency in project["dependencies"])
    assert "click" in {dependency["name"] for dependency in package["dependencies"]}


def test_claude_review_runs_only_when_pull_request_opens() -> None:
    # Preserve GitHub's `on` key instead of interpreting it as a YAML 1.1 boolean.
    workflow = yaml.load(
        (REPO_ROOT / ".github" / "workflows" / "claude-code-review.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"] == {"pull_request": {"types": ["opened"]}}
