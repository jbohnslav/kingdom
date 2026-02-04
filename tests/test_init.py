from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from kingdom import cli
from kingdom.state import ensure_base_layout, ensure_run_layout, state_root


def test_ensure_base_layout_creates_structure(tmp_path: Path) -> None:
    """ensure_base_layout creates .kd/ with expected directories and files."""
    paths = ensure_base_layout(tmp_path)

    assert (tmp_path / ".kd").is_dir()
    assert (tmp_path / ".kd" / "runs").is_dir()
    assert (tmp_path / ".kd" / "worktrees").is_dir()
    assert (tmp_path / ".kd" / "config.json").exists()
    assert (tmp_path / ".kd" / ".gitignore").exists()

    assert paths["state_root"] == tmp_path / ".kd"
    assert paths["runs_root"] == tmp_path / ".kd" / "runs"
    assert paths["worktrees_root"] == tmp_path / ".kd" / "worktrees"


def test_ensure_base_layout_idempotent(tmp_path: Path) -> None:
    """ensure_base_layout can be called multiple times safely."""
    paths1 = ensure_base_layout(tmp_path)
    paths2 = ensure_base_layout(tmp_path)

    assert paths1 == paths2
    assert (tmp_path / ".kd").is_dir()


def test_ensure_base_layout_skips_gitignore_when_requested(tmp_path: Path) -> None:
    """ensure_base_layout respects create_gitignore=False."""
    paths = ensure_base_layout(tmp_path, create_gitignore=False)

    assert (tmp_path / ".kd").is_dir()
    assert not (tmp_path / ".kd" / ".gitignore").exists()
    assert paths["gitignore"] is None


def test_ensure_run_layout_creates_tickets_and_learnings(tmp_path: Path) -> None:
    """ensure_run_layout creates tickets/ dir and learnings.md file."""
    paths = ensure_run_layout(tmp_path, "test-feature")

    assert (tmp_path / ".kd" / "runs" / "test-feature" / "tickets").is_dir()
    assert (tmp_path / ".kd" / "runs" / "test-feature" / "learnings.md").exists()
    assert paths["tickets_root"] == tmp_path / ".kd" / "runs" / "test-feature" / "tickets"
    assert paths["learnings_md"] == tmp_path / ".kd" / "runs" / "test-feature" / "learnings.md"


def test_cli_init_creates_structure() -> None:
    """kd init creates .kd/ directory structure."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        # Create a git repo for the test
        subprocess.run(["git", "init", "-q"], check=True)

        result = runner.invoke(cli.app, ["init"])

        assert result.exit_code == 0
        assert "Initialized" in result.output
        assert (base / ".kd").is_dir()
        assert (base / ".kd" / "runs").is_dir()
        assert (base / ".kd" / "worktrees").is_dir()
        assert (base / ".kd" / "config.json").exists()
        assert (base / ".kd" / ".gitignore").exists()


def test_cli_init_requires_git_repo() -> None:
    """kd init fails when not in a git repo."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli.app, ["init"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output


def test_cli_init_no_git_flag_skips_check() -> None:
    """kd init --no-git works without a git repo."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()

        result = runner.invoke(cli.app, ["init", "--no-git"])

        assert result.exit_code == 0
        assert (base / ".kd").is_dir()


def test_cli_init_no_gitignore_flag() -> None:
    """kd init --no-gitignore skips .gitignore creation."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        result = runner.invoke(cli.app, ["init", "--no-gitignore"])

        assert result.exit_code == 0
        assert (base / ".kd").is_dir()
        assert not (base / ".kd" / ".gitignore").exists()


def test_cli_init_idempotent() -> None:
    """kd init can be run multiple times."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)

        result1 = runner.invoke(cli.app, ["init"])
        result2 = runner.invoke(cli.app, ["init"])

        assert result1.exit_code == 0
        assert result2.exit_code == 0


def test_gitignore_content_matches_spec() -> None:
    """The generated .gitignore matches the architecture doc."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        runner.invoke(cli.app, ["init"])

        gitignore = (base / ".kd" / ".gitignore").read_text()
        assert "*.json" in gitignore
        assert "*.jsonl" in gitignore
        assert "runs/**/logs/" in gitignore
        assert "worktrees/" in gitignore


def test_cli_start_auto_init_requires_git_repo() -> None:
    """kd start fails when auto-initializing in a non-git directory."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli.app, ["start", "test-feature"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output
