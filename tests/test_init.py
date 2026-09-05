from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from kingdom.cli import app
from kingdom.cli.helpers import (
    SKILL_MANIFEST,
    content_hash,
    install_skill,
    install_skill_target,
    read_skill_manifest,
    skill_install_targets,
    write_skill_bundle,
)
from kingdom.state import (
    branch_root,
    ensure_base_layout,
    ensure_branch_layout,
    read_execution_ticket_context,
    read_json,
    record_execution_ticket_context,
    resolve_execution_context,
    set_current_run,
    write_json,
)
from kingdom.ticket import Ticket, write_ticket

SKILL_REFERENCE_FILES = {"council.md", "peasants.md", "tickets.md"}


def assert_skill_files_copied(skill_dir: Path) -> None:
    assert (skill_dir / "SKILL.md").exists()
    reference_files = {path.name for path in (skill_dir / "references").iterdir()}
    assert reference_files >= SKILL_REFERENCE_FILES


def test_ensure_base_layout_creates_structure(tmp_path: Path) -> None:
    """ensure_base_layout creates .kd/ with expected directories and files."""
    paths = ensure_base_layout(tmp_path)

    assert (tmp_path / ".kd").is_dir()
    assert (tmp_path / ".kd" / "worktrees").is_dir()
    assert (tmp_path / ".kd" / ".gitignore").exists()
    init_script = tmp_path / ".kd" / "init-worktree.sh"
    assert init_script.exists()
    assert init_script.stat().st_mode & 0o111  # executable

    assert paths["state_root"] == tmp_path / ".kd"
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


def test_cli_start_kd_base_invalid_hard_fails(tmp_path: Path) -> None:
    """kd start with KD_BASE set to an invalid path errors instead of auto-initializing."""
    runner = CliRunner()
    bad_path = tmp_path / "nonsense"
    bad_path.mkdir()
    with patch.dict("os.environ", {"KD_BASE": str(bad_path)}):
        result = runner.invoke(app, ["start", "test-branch"])
    assert result.exit_code == 1
    assert "KD_BASE=" in result.output
    assert "does not contain a .kd/" in result.output


def test_cli_start_kd_base_unset_keeps_auto_init() -> None:
    """kd start without KD_BASE and no .kd/ falls through to auto-init."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        result = runner.invoke(app, ["start", "test-feature"])

        assert result.exit_code == 0
        assert "Auto-initializing" in result.output
        assert (Path.cwd() / ".kd" / "branches" / "test-feature").is_dir()


def test_cli_start_preserves_legacy_runs_hard_boundary() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        ensure_base_layout(base)
        legacy_runs = base / ".kd" / "runs"
        legacy_runs.mkdir()
        (legacy_runs / "old-feature").mkdir()

        result = runner.invoke(app, ["start", "test-feature"])

        assert result.exit_code == 1
        output = " ".join(result.output.splitlines())
        assert "Legacy .kd/runs/ directory found. Rename it to .kd/branches/ manually and retry." in output
        assert "Auto-initializing" not in result.output
        assert not (base / ".kd" / "branches" / "test-feature").exists()


def test_cli_start_auto_init_from_subdirectory_uses_git_root() -> None:
    """kd start from a subdirectory auto-initializes .kd/ at the git root, not cwd."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        git_root = Path.cwd()
        subdir = git_root / "src" / "deep"
        subdir.mkdir(parents=True)
        with patch("kingdom.state.Path.cwd", return_value=subdir):
            result = runner.invoke(app, ["start", "test-feature"])
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
            result = runner.invoke(app, ["start", "test-feature"])
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
            result = runner.invoke(app, ["start", "test-feature"])
    assert result.exit_code == 0
    assert "Auto-initializing" in result.output


def test_cli_start_auto_init_requires_git_repo() -> None:
    """kd start fails when auto-initializing in a non-git directory."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["start", "test-feature"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output


def test_cli_start_auto_init_installs_skill(tmp_path: Path) -> None:
    """kd start auto-init should also install the skill."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    runner = CliRunner()

    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True)
        with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
            result = runner.invoke(app, ["start", "test-feature"])

    assert result.exit_code == 0
    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    assert (skill_dir / "SKILL.md").exists()


def test_cli_start_existing_workspace_does_not_refresh_skill() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        ensure_base_layout(base)
        ensure_branch_layout(base, "feature/existing")

        with patch("kingdom.cli.install_skill") as installer:
            resume_result = runner.invoke(app, ["start", "feature/existing"])
            new_branch_result = runner.invoke(app, ["start", "feature/new"])

        assert resume_result.exit_code == 0
        assert new_branch_result.exit_code == 0
        installer.assert_not_called()


def test_cli_start_initializes_ticket_workspace_without_planning_docs() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch = "feature/test-start"
        result = runner.invoke(app, ["start", branch])

        assert result.exit_code == 0
        assert f"Started workspace for branch {branch}" in result.output

        branch_dir = branch_root(base, branch)
        assert (branch_dir / "tickets").is_dir()
        assert not (branch_dir / "design.md").exists()
        assert not (branch_dir / "breakdown.md").exists()
        assert "Tickets: 0 branch, 0 backlog" in result.output
        assert 'Next: kd tk create "<title>"' in result.output
        assert "--type epic" in result.output


def test_cli_start_resumes_existing_workspace_without_overwriting_content() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        branch = "feature/test-start"
        start_result = runner.invoke(app, ["start", branch])
        assert start_result.exit_code == 0

        branch_dir = branch_root(base, branch)
        design_path = branch_dir / "design.md"
        design_path.write_text("# Legacy design\n", encoding="utf-8")
        write_ticket(Ticket(id="task1", status="open", title="Existing task"), branch_dir / "tickets" / "task1.md")

        resume_result = runner.invoke(app, ["start", branch])

        assert resume_result.exit_code == 0
        assert f"Resumed workspace for branch {branch}" in resume_result.output
        assert "Tickets: 1 branch, 0 backlog" in resume_result.output
        assert "Next: kd tk list --ready" in resume_result.output
        assert design_path.read_text(encoding="utf-8") == "# Legacy design\n"


def test_cli_start_changes_workspace_default_without_force() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        ensure_branch_layout(base, "feature/previous")
        set_current_run(base, "feature-previous")

        result = runner.invoke(app, ["start", "feature/next"])

        assert result.exit_code == 0
        assert (base / ".kd" / "current").read_text(encoding="utf-8") == "feature-next\n"
        assert "Started workspace for branch feature/next" in result.output


def test_cli_start_selects_existing_workspace_as_default() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        ensure_branch_layout(base, "feature/previous")
        ensure_branch_layout(base, "feature/existing")
        set_current_run(base, "feature-previous")

        result = runner.invoke(app, ["start", "feature/existing"])

        assert result.exit_code == 0, result.output
        assert (base / ".kd" / "current").read_text(encoding="utf-8") == "feature-existing\n"
        assert "Resumed workspace for branch feature/existing" in result.output


def test_cli_start_help_describes_workspace_selection() -> None:
    result = CliRunner().invoke(app, ["start", "--help"])

    assert result.exit_code == 0
    assert "Initialize, resume, or select a branch workspace" in " ".join(result.output.split())


def test_cli_start_reactivates_done_workspace_without_changing_tickets() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        branch = "feature/legacy-done"
        branch_dir = ensure_branch_layout(base, branch)
        ticket_path = branch_dir / "tickets" / "done1.md"
        write_ticket(Ticket(id="done1", status="closed", title="Finished task"), ticket_path)
        ticket_history = ticket_path.read_text(encoding="utf-8")
        write_json(
            branch_dir / "state.json",
            {
                "branch": branch,
                "status": "done",
                "done_at": "2026-08-01T12:00:00+00:00",
            },
        )

        result = runner.invoke(app, ["start", branch])

        assert result.exit_code == 0, result.output
        state = read_json(branch_dir / "state.json")
        assert state == {"branch": branch}
        assert ticket_path.read_text(encoding="utf-8") == ticket_history


def test_cli_start_does_not_move_execution_context_binding() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        source = "feature/context-owner"
        target = "feature/selected-default"
        ensure_branch_layout(base, source)
        ensure_branch_layout(base, target)
        set_current_run(base, source)

        with patch.dict("os.environ", {"KD_CONTEXT": "start-independence"}, clear=True):
            context = resolve_execution_context()
            assert context is not None
            record_execution_ticket_context(base, context, "task1", feature=source)
            binding = read_execution_ticket_context(base, context)
            result = runner.invoke(app, ["start", target])
            updated_binding = read_execution_ticket_context(base, context)

        assert result.exit_code == 0, result.output
        assert (base / ".kd" / "current").read_text(encoding="utf-8") == "feature-selected-default\n"
        assert updated_binding == binding
        assert updated_binding is not None
        assert updated_binding["feature"] == "feature-context-owner"


def test_cli_start_with_only_closed_tickets_suggests_new_work() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        branch = "feature/complete"
        branch_dir = ensure_branch_layout(base, branch)
        write_ticket(
            Ticket(id="done1", status="closed", title="Finished task"),
            branch_dir / "tickets" / "done1.md",
        )

        result = runner.invoke(app, ["start", branch])

        assert result.exit_code == 0
        assert 'Next: kd tk create "<title>"' in result.output
        assert "kd tk list --ready" not in result.output


def test_cli_start_with_blocked_tickets_suggests_blocked_list() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        branch = "feature/blocked"
        branch_dir = ensure_branch_layout(base, branch)
        write_ticket(
            Ticket(id="wait1", status="open", title="Waiting task", deps=["missing"]),
            branch_dir / "tickets" / "wait1.md",
        )

        result = runner.invoke(app, ["start", branch])

        assert result.exit_code == 0
        assert "Next: kd tk list --blocked" in result.output
        assert "kd tk list --ready" not in result.output


def test_cli_start_uses_global_dependency_status_for_ready_work() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)

        done_dir = ensure_branch_layout(base, "feature/done")
        write_ticket(
            Ticket(id="done1", status="closed", title="Completed dependency"),
            done_dir / "tickets" / "done1.md",
        )
        write_json(done_dir / "state.json", {"branch": "feature/done", "status": "done"})

        branch = "feature/dependent"
        branch_dir = ensure_branch_layout(base, branch)
        write_ticket(
            Ticket(id="next1", status="open", title="Ready task", deps=["done1"]),
            branch_dir / "tickets" / "next1.md",
        )

        start_result = runner.invoke(app, ["start", branch])
        ready_result = runner.invoke(app, ["tk", "list", "--ready"])

        assert start_result.exit_code == 0
        assert ready_result.exit_code == 0
        assert "Next: kd tk list --ready" in start_result.output
        assert "next1" in ready_result.output


def test_install_skill_copies_files(tmp_path: Path) -> None:
    """install_skill copies SKILL.md and references to Claude's skill dir."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    assert result == "refreshed"
    assert_skill_files_copied(skill_dir)

    # Verify content is non-empty
    assert len((skill_dir / "SKILL.md").read_text()) > 100


def test_install_skill_uses_explicit_target_home(monkeypatch, tmp_path: Path) -> None:
    skill_home = tmp_path / "isolated-agent-home"
    skill_home.mkdir()
    monkeypatch.setenv("KD_SKILL_HOME", str(skill_home))

    with patch("kingdom.cli.helpers.Path.home", side_effect=AssertionError("host home was read")):
        result = install_skill()

    assert result == "refreshed"
    assert_skill_files_copied(skill_home / ".claude" / "skills" / "kingdom")


def test_skill_install_targets_include_cursor_and_codex_when_roots_exist(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".cursor").mkdir()
    (fake_home / ".codex").mkdir()

    targets = skill_install_targets(fake_home)

    assert fake_home / ".claude" / "skills" / "kingdom" in targets
    assert fake_home / ".cursor" / "skills" / "kingdom" in targets
    assert fake_home / ".codex" / "skills" / "kingdom" in targets


def test_skill_install_targets_skip_missing_cursor_and_codex_roots(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    targets = skill_install_targets(fake_home)

    assert targets == [fake_home / ".claude" / "skills" / "kingdom"]
    assert not (fake_home / ".cursor").exists()
    assert not (fake_home / ".codex").exists()


def test_install_skill_copies_files_to_cursor_when_root_exists(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".cursor").mkdir()

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    skill_dir = fake_home / ".cursor" / "skills" / "kingdom"
    assert result == "refreshed"
    assert_skill_files_copied(skill_dir)


def test_install_skill_copies_files_to_codex_when_root_exists(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".codex").mkdir()

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    skill_dir = fake_home / ".codex" / "skills" / "kingdom"
    assert result == "refreshed"
    assert_skill_files_copied(skill_dir)


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

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    # Should still be a symlink, not overwritten
    assert result == "skipped"
    assert skill_dir.is_symlink()
    assert not (skill_dir / "SKILL.md").exists()


def test_install_skill_installs_cursor_when_claude_target_is_symlink(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    cursor_root = fake_home / ".cursor"
    claude_skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    cursor_root.mkdir(parents=True)
    claude_skill_dir.mkdir(parents=True)

    real_target = tmp_path / "real_skill"
    real_target.mkdir()
    claude_skill_dir.rmdir()
    claude_skill_dir.symlink_to(real_target)

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    assert result == "refreshed"
    assert claude_skill_dir.is_symlink()
    assert not (claude_skill_dir / "SKILL.md").exists()
    assert_skill_files_copied(fake_home / ".cursor" / "skills" / "kingdom")


def test_install_skill_idempotent(tmp_path: Path) -> None:
    """install_skill can be called multiple times without error."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        assert install_skill() == "refreshed"
        assert install_skill() == "skipped"

    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    assert (skill_dir / "SKILL.md").exists()


def test_install_skill_target_removes_unmodified_retired_files(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    current_files = {
        "SKILL.md": b"current skill\n",
        "references/retired.md": b"retired reference\n",
    }
    next_files = {"SKILL.md": b"current skill\n"}
    write_skill_bundle(target, current_files)

    status, note = install_skill_target(target, next_files)

    assert (status, note) == ("updated", "managed files refreshed")
    assert not (target / "references" / "retired.md").exists()
    assert read_skill_manifest(target / SKILL_MANIFEST) == {"SKILL.md": content_hash(next_files["SKILL.md"])}


def test_install_skill_target_preserves_modified_retired_files(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    current_files = {
        "SKILL.md": b"old skill\n",
        "references/retired.md": b"managed reference\n",
    }
    next_files = {"SKILL.md": b"new skill\n"}
    write_skill_bundle(target, current_files)
    retired = target / "references" / "retired.md"
    retired.write_bytes(b"user customization\n")

    status, note = install_skill_target(target, next_files)

    assert (status, note) == ("updated", "managed files refreshed")
    assert (target / "SKILL.md").read_bytes() == next_files["SKILL.md"]
    assert retired.read_bytes() == b"user customization\n"
    assert read_skill_manifest(target / SKILL_MANIFEST) == {"SKILL.md": content_hash(next_files["SKILL.md"])}
    assert install_skill_target(target, next_files) == ("skipped", "already current")
    assert retired.read_bytes() == b"user customization\n"


def test_install_skill_target_rejects_manifest_paths_outside_target(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"previously managed\n")
    write_json(
        target / SKILL_MANIFEST,
        {
            "schema_version": 1,
            "files": {"../outside.md": content_hash(outside.read_bytes())},
        },
    )

    result = install_skill_target(target, {"SKILL.md": b"current skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert outside.read_bytes() == b"previously managed\n"
    assert not (target / "SKILL.md").exists()


def test_install_skill_target_rejects_retired_file_through_symlinked_parent(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    retired = outside / "retired.md"
    retired.write_bytes(b"previously managed\n")
    (target / "references").symlink_to(outside, target_is_directory=True)
    write_json(
        target / SKILL_MANIFEST,
        {
            "schema_version": 1,
            "files": {"references/retired.md": content_hash(retired.read_bytes())},
        },
    )

    result = install_skill_target(target, {"SKILL.md": b"current skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert retired.read_bytes() == b"previously managed\n"
    assert not (target / "SKILL.md").exists()


def test_install_skill_target_rejects_retired_file_symlink(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"previously managed\n")
    retired = target / "retired.md"
    retired.symlink_to(outside)
    write_json(
        target / SKILL_MANIFEST,
        {
            "schema_version": 1,
            "files": {"retired.md": content_hash(outside.read_bytes())},
        },
    )

    result = install_skill_target(target, {"SKILL.md": b"current skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert retired.is_symlink()
    assert outside.read_bytes() == b"previously managed\n"
    assert not (target / "SKILL.md").exists()


def test_install_skill_target_rejects_nul_manifest_path(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    write_json(
        target / SKILL_MANIFEST,
        {
            "schema_version": 1,
            "files": {"references/retired\0.md": content_hash(b"managed\n")},
        },
    )

    result = install_skill_target(target, {"SKILL.md": b"current skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert not (target / "SKILL.md").exists()


def test_install_skill_target_rejects_manifest_path_resolution_error(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    loop = target / "loop"
    loop.symlink_to(loop)
    write_json(
        target / SKILL_MANIFEST,
        {
            "schema_version": 1,
            "files": {"loop/retired.md": content_hash(b"managed\n")},
        },
    )

    result = install_skill_target(target, {"SKILL.md": b"current skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert not (target / "SKILL.md").exists()


def test_install_skill_target_rejects_new_file_through_symlinked_parent(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (target / "references").symlink_to(outside, target_is_directory=True)

    result = install_skill_target(target, {"references/new.md": b"new reference\n"})

    assert result == ("manual", "bundled skill paths are invalid")
    assert not (outside / "new.md").exists()
    assert not (target / SKILL_MANIFEST).exists()


def test_install_skill_target_rejects_live_manifest_symlink(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    skill = target / "SKILL.md"
    skill.write_bytes(b"old skill\n")
    outside_manifest = tmp_path / "outside-manifest.json"
    write_json(
        outside_manifest,
        {
            "schema_version": 1,
            "files": {"SKILL.md": content_hash(skill.read_bytes())},
        },
    )
    original_manifest = outside_manifest.read_bytes()
    (target / SKILL_MANIFEST).symlink_to(outside_manifest)

    result = install_skill_target(target, {"SKILL.md": b"new skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert skill.read_bytes() == b"old skill\n"
    assert outside_manifest.read_bytes() == original_manifest


def test_install_skill_target_rejects_dangling_manifest_symlink(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    target.mkdir()
    outside_manifest = tmp_path / "missing" / "outside-manifest.json"
    manifest = target / SKILL_MANIFEST
    manifest.symlink_to(outside_manifest)

    result = install_skill_target(target, {"SKILL.md": b"new skill\n"})

    assert result == ("manual", "managed-file manifest is invalid")
    assert manifest.is_symlink()
    assert not outside_manifest.exists()
    assert not (target / "SKILL.md").exists()


def test_install_skill_target_rejects_regular_file_as_incoming_parent(tmp_path: Path) -> None:
    target = tmp_path / "kingdom"
    current_files = {
        "SKILL.md": b"old skill\n",
        "retired.md": b"retired reference\n",
    }
    write_skill_bundle(target, current_files)
    manifest = target / SKILL_MANIFEST
    original_manifest = manifest.read_bytes()
    references = target / "references"
    references.write_bytes(b"user file\n")

    result = install_skill_target(
        target,
        {
            "SKILL.md": b"new skill\n",
            "references/new.md": b"new reference\n",
        },
    )

    assert result == ("manual", "bundled skill paths are invalid")
    assert (target / "SKILL.md").read_bytes() == current_files["SKILL.md"]
    assert (target / "retired.md").read_bytes() == current_files["retired.md"]
    assert references.read_bytes() == b"user file\n"
    assert manifest.read_bytes() == original_manifest


def test_install_skill_reports_each_supported_host(tmp_path: Path, capsys) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    output = capsys.readouterr().out
    assert result == "refreshed"
    assert "claude: updated" in output
    assert "codex: skipped" in output
    assert "cursor: skipped" in output


def test_install_skill_preserves_unknown_existing_skill(tmp_path: Path, capsys) -> None:
    fake_home = tmp_path / "home"
    skill_dir = fake_home / ".claude" / "skills" / "kingdom"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("user customization\n", encoding="utf-8")

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        result = install_skill()

    assert result == "failed"
    assert skill_file.read_text(encoding="utf-8") == "user customization\n"
    assert "claude: manual action needed" in capsys.readouterr().out


def test_install_skill_preserves_modified_managed_skill(tmp_path: Path, capsys) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        assert install_skill() == "refreshed"
        skill_file = fake_home / ".claude" / "skills" / "kingdom" / "SKILL.md"
        skill_file.write_text("managed, then customized\n", encoding="utf-8")
        result = install_skill()

    assert result == "failed"
    assert skill_file.read_text(encoding="utf-8") == "managed, then customized\n"
    assert "claude: manual action needed" in capsys.readouterr().out


def test_install_skill_permission_error_warns(tmp_path: Path) -> None:
    """install_skill should warn and continue when target dir is unwritable."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    # Make .claude read-only so mkdir inside it fails
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir()
    claude_dir.chmod(0o444)

    with patch("kingdom.cli.helpers.Path.home", return_value=fake_home):
        # Should not raise — just warn
        install_skill()

    # Restore permissions for cleanup
    claude_dir.chmod(0o755)


def test_install_skill_runtime_error_warns() -> None:
    """install_skill should warn and continue when Path.home() raises RuntimeError."""
    with patch("kingdom.cli.helpers.Path.home", side_effect=RuntimeError("no home")):
        install_skill()  # should not raise


def test_legacy_runs_guard_shows_clean_cli_error() -> None:
    """kd status with non-empty .kd/runs/ should show a clean error, not a traceback."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        base = Path.cwd()
        subprocess.run(["git", "init", "-q"], check=True)
        ensure_base_layout(base)
        runs_dir = base / ".kd" / "runs"
        runs_dir.mkdir()
        (runs_dir / "old-branch").mkdir()

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Legacy .kd/runs/ directory found" in result.output
        assert "Traceback" not in result.output
