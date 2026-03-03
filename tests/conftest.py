"""Ensure tests import kingdom from this worktree, not from an external editable install."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kingdom.state import ensure_branch_layout, set_current_run

# Prepend this worktree's src/ so tests always use local code,
# even when pytest is invoked by a Python from a different venv.
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-textual-integration",
        action="store_true",
        default=False,
        help="Run Textual integration tests (slow, uses app.run_test() + Pilot)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-textual-integration"):
        return
    skip = pytest.mark.skip(reason="needs --run-textual-integration flag to run")
    for item in items:
        if "textual_integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def clear_kd_base(monkeypatch):
    """Prevent KD_BASE from the developer's environment leaking into tests."""
    monkeypatch.delenv("KD_BASE", raising=False)


# ---------------------------------------------------------------------------
# Shared project fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def branch_name(request: pytest.FixtureRequest) -> str:
    """Read BRANCH constant from the test module, defaulting to a generic name."""
    return getattr(request.module, "BRANCH", "feature/test-branch")


@pytest.fixture()
def project(tmp_path: Path, branch_name: str) -> Path:
    """Create a minimal project with branch layout."""
    ensure_branch_layout(tmp_path, branch_name)
    return tmp_path


@pytest.fixture()
def project_with_run(tmp_path: Path, branch_name: str) -> Path:
    """Create a minimal project with branch layout and set current run."""
    ensure_branch_layout(tmp_path, branch_name)
    set_current_run(tmp_path, branch_name)
    return tmp_path


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Shared CliRunner instance for CLI tests."""
    return CliRunner()


@pytest.fixture()
def cli_project(branch_name: str) -> Generator[Path, None, None]:
    """Create an isolated filesystem project for CLI tests.

    Combines CliRunner.isolated_filesystem(), ensure_branch_layout(),
    and set_current_run() into a single fixture.
    """
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        ensure_branch_layout(base, branch_name)
        set_current_run(base, branch_name)
        yield base
