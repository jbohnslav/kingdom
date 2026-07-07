import tomllib
from pathlib import Path


def dependency_names(dependencies: list[str]) -> set[str]:
    return {
        dependency.split(";", 1)[0]
        .split("[", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .split("~", 1)[0]
        .strip()
        .lower()
        .replace("_", "-")
        for dependency in dependencies
    }


def test_click_is_a_direct_runtime_dependency() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "click" in dependency_names(pyproject["project"]["dependencies"])
