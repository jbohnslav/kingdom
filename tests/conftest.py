"""Ensure tests import kingdom from this worktree, not from an external editable install."""

import sys
from pathlib import Path

import pytest

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
