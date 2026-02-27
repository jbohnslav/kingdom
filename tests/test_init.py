from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom import cli
from kingdom.cli import install_skill
from kingdom.state import branch_root, ensure_base_layout, ensure_run_layout


def test_ensure_base_layout_creates_structure(tmp_path: Path) -> None:
    """ensure_base_layout creates .kd/ with expected directories and files."""
    paths = ensure_base_layout(tmp_path)

    assert (tmp_path / ".kd").is_dir()
    assert (tmp_path / ".kd" / "runs").is_dir()
    assert (tmp_path / ".kd" / "worktrees").is_dir()
    assert (tmp_path / ".kd" / ".gitignore").exists()
    init_script = tmp_path / ".kd" / "init-worktree.sh"
    assert init_script.exists()
    assert init_script.stat().st_mode & 0o111  # executable

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


def test_cli_start_kd_base_invalid_hard_fails(tmp_path: Path) -> None:
    """kd start with KD_BASE set to an invalid path errors instead of auto-initializing."""
    runner = CliRunner()
    bad_path = tmp_path / "nonsense"
    bad_path.mkdir()
    with patch.dict("os.environ", {"KD_BASE": str(bad_path)}):
        result = runner.invoke(cli.app, ["start", "test-branch"])
    assert result.exit_code == 1
    assert "KD_BASE=" in result.output
    assert "does not contain a .kd/" in result.output


def test_cli_start_kd_base_unset_keeps_auto_init() -> None:
    """kd start without KD_BASE and no .kd/ falls through to auto-init."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        result = runner.invoke(cli.app, ["start", "test-feature"])
    assert result.exit_code == 0
    assert "Auto-initializing" in result.output


def test_cli_start_auto_init_from_subdirectory_uses_git_root() -> None:
    """kd start from a subdirectory auto-initializes .kd/ at the git root, not cwd."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        git_root = Path.cwd()
        subdir = git_root / "src" / "deep"
        subdir.mkdir(parents=True)
        with patch("kingdom.state.Path.cwd", return_value=subdir):
            result = runner.invoke(cli.app, ["start", "test-feature"])
        assert result.exit_code == 0
        assert "Auto-initializing" in result.output
        # .kd/ should be at git root, not in the subdirectory
        assert (git_root / ".kd").is_dir()
        assert not (subdir / ".kd").exists()


def test_cli_start_from_subdirectory_with_existing_kd() -> None:
    """kd start from a subdirectory finds .kd/ at repo root via parent walk."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        git_root = Path.cwd()
        ensure_base_layout(git_root)
        subdir = git_root / "src" / "deep"
        subdir.mkdir(parents=True)
        with patch("kingdom.state.Path.cwd", return_value=subdir):
            result = runner.invoke(cli.app, ["start", "test-feature"])
        assert result.exit_code == 0
        # Should NOT have created a second .kd/ in the subdirectory
        assert not (subdir / ".kd").exists()


def test_cli_start_auto_init_handles_git_timeout() -> None:
    """kd start should not crash if git rev-parse --show-toplevel times out."""
    runner = CliRunner()
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if "--show-toplevel" in cmd:
            raise subprocess.TimeoutExpired(cmd, 5)
        return real_run(cmd, **kwargs)

    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        with patch("kingdom.cli.subprocess.run", side_effect=fake_run):
            result = runner.invoke(cli.app, ["start", "test-feature"])
    assert result.exit_code == 0
    assert "Auto-initializing" in result.output


def test_cli_start_auto_init_requires_git_repo() -> None:
    """kd start fails when auto-initializing in a non-git directory."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli.app, ["start", "test-feature"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output


def test_cli_start_auto_init_installs_skill(tmp_path: Path) -> None:
    """kd start auto-init should also install the skill."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runner = CliRunner()

    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        with patch("kingdom.cli.Path.home", return_value=fake_home):
            result = runner.invoke(cli.app, ["start", "test-feature"])

    assert result.exit_code == 0
    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    assert (skill_dir / "SKILL.md").exists()


def test_cli_start_initializes_design_and_prints_path() -> None:
    """kd start should create design.md from template and print its location."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch = "feature/test-start"
        result = runner.invoke(cli.app, ["start", branch])

        assert result.exit_code == 0
        assert f"Started session for branch {branch}" in result.output

        design_path = branch_root(base, branch) / "design.md"
        assert design_path.exists()
        assert "Design: feature/test-start" in design_path.read_text(encoding="utf-8")
        assert f"Design: {design_path}" in result.output


def test_cli_design_prints_path_after_start() -> None:
    """Running kd design after kd start should print the design path."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch = "feature/test-start"
        start_result = runner.invoke(cli.app, ["start", branch])
        assert start_result.exit_code == 0

        design_path = branch_root(base, branch) / "design.md"
        before = design_path.read_text(encoding="utf-8")

        design_result = runner.invoke(cli.app, ["design"])
        assert design_result.exit_code == 0
        assert design_result.output.strip().endswith("design.md")
        assert design_path.read_text(encoding="utf-8") == before


def test_install_skill_copies_files(tmp_path: Path) -> None:
    """install_skill copies SKILL.md and references to ~/.claude/skills/kingdom/."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with patch("kingdom.cli.Path.home", return_value=fake_home):
        install_skill()

    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "references" / "council.md").exists()
    assert (skill_dir / "references" / "peasants.md").exists()
    assert (skill_dir / "references" / "tickets.md").exists()

    # Verify content is non-empty
    assert len((skill_dir / "SKILL.md").read_text()) > 100


def test_install_skill_skips_symlink(tmp_path: Path) -> None:
    """install_skill should not overwrite a dev symlink."""
    fake_home = tmp_path / "home"
    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    skill_dir.mkdir(parents=True)

    # Create a symlink to simulate dev setup
    real_target = tmp_path / "real_skill"
    real_target.mkdir()
    skill_dir.rmdir()
    skill_dir.symlink_to(real_target)

    with patch("kingdom.cli.Path.home", return_value=fake_home):
        install_skill()

    # Should still be a symlink, not overwritten
    assert skill_dir.is_symlink()
    assert not (skill_dir / "SKILL.md").exists()


def test_install_skill_idempotent(tmp_path: Path) -> None:
    """install_skill can be called multiple times without error."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with patch("kingdom.cli.Path.home", return_value=fake_home):
        install_skill()
        install_skill()

    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    assert (skill_dir / "SKILL.md").exists()


def test_install_skill_permission_error_warns(tmp_path: Path) -> None:
    """install_skill should warn and continue when target dir is unwritable."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    # Make .claude read-only so mkdir inside it fails
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    claude_dir.chmod(0o444)

    with patch("kingdom.cli.Path.home", return_value=fake_home):
        # Should not raise — just warn
        cli.install_skill()

    # Restore permissions for cleanup
    claude_dir.chmod(0o755)


def test_install_skill_runtime_error_warns() -> None:
    """install_skill should warn and continue when Path.home() raises RuntimeError."""
    with patch("kingdom.cli.Path.home", side_effect=RuntimeError("no home")):
        cli.install_skill()  # should not raise
