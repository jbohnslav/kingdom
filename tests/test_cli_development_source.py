from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app, development_source_warning

runner = CliRunner()


def make_checkout(root: Path) -> Path:
    module_file = root / "src" / "kingdom" / "cli" / "__init__.py"
    module_file.parent.mkdir(parents=True)
    module_file.touch()
    (root / "pyproject.toml").touch()
    return module_file


def test_installed_cli_warns_inside_development_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "kingdom"
    make_checkout(checkout)
    installed_module = tmp_path / "tools" / "kingdom" / "cli" / "__init__.py"

    warning = development_source_warning(checkout / "tests", installed_module)

    assert warning is not None
    assert "not running from this Kingdom checkout" in warning
    assert "uv run kd" in warning


def test_working_tree_cli_is_quiet_inside_development_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "kingdom"
    working_tree_module = make_checkout(checkout)

    assert development_source_warning(checkout, working_tree_module) is None


def test_installed_cli_is_quiet_outside_development_checkout(tmp_path: Path) -> None:
    installed_module = tmp_path / "tools" / "kingdom" / "cli" / "__init__.py"

    assert development_source_warning(tmp_path / "ordinary-project", installed_module) is None


def test_top_level_callback_prints_development_source_warning(cli_project: Path) -> None:
    warning = "Warning: use uv run kd"

    with patch("kingdom.cli.development_source_warning", return_value=warning):
        result = runner.invoke(app, ["status"], env={"KD_BASE": str(cli_project)})

    assert result.exit_code == 0
    assert warning in result.stderr
