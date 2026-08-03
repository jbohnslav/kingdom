import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_uv_and_pre_commit_pin_the_same_ruff_version() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    ruff_dependency = next(
        dependency for dependency in pyproject["dependency-groups"]["dev"] if dependency.startswith("ruff")
    )
    assert ruff_dependency.startswith("ruff==")
    uv_version = ruff_dependency.removeprefix("ruff==")

    pre_commit = (REPO_ROOT / ".pre-commit-config.yaml").read_text()
    ruff_repo = pre_commit.split("repo: https://github.com/astral-sh/ruff-pre-commit", 1)[1].split("\n  - repo:", 1)[0]
    hook_version = re.search(r"rev: v([^\s]+)", ruff_repo)

    assert hook_version is not None
    assert hook_version.group(1) == uv_version


def test_readme_documents_canonical_ruff_checks() -> None:
    readme = (REPO_ROOT / "README.md").read_text()

    for command in (
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run pre-commit run ruff --all-files",
        "uv run pre-commit run ruff-format --all-files",
    ):
        assert command in readme
