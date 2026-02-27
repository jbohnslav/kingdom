"""Shared CLI helper utilities for the Kingdom CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

from kingdom.state import find_project_root, read_json, state_root
from kingdom.ticket import AmbiguousTicketMatch, Ticket, find_ticket

from .display import print_error

VERBOSE: bool = False


def verbose_echo(message: str) -> None:
    """Print a debug message to stderr when --verbose is set."""
    import kingdom.cli as _cli

    if not _cli.VERBOSE:
        return
    _cli.error_console.print(f"[dim]{message}[/dim]")


def resolve_ticket_or_exit(
    base: Path,
    ticket_id: str,
    *,
    not_found_label: str = "Ticket not found",
    branch: str | None = None,
) -> tuple[Ticket, Path]:
    """Find a ticket by ID or exit with a clear error.

    Handles ``AmbiguousTicketMatch`` and not-found cases with consistent
    error messages and exit code 1.
    """
    try:
        result = find_ticket(base, ticket_id, branch=branch)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None
    if result is None:
        print_error(f"{not_found_label}: {ticket_id}")
        raise typer.Exit(code=1)
    return result


def run_init_script(base: Path, worktree_path: Path, *, step_prefix: str = "") -> None:
    """Run ``.kd/init-worktree.sh`` if present and executable."""
    init_script = state_root(base) / "init-worktree.sh"
    if init_script.exists() and os.access(init_script, os.X_OK):
        typer.echo(f"{step_prefix}Running init-worktree.sh...")
        init_result = subprocess.run(
            [str(init_script), str(worktree_path)],
            capture_output=True,
            text=True,
        )
        if init_result.stdout.strip():
            typer.echo(init_result.stdout.strip())
        if init_result.returncode != 0:
            typer.echo(f"Warning: init-worktree.sh failed (exit {init_result.returncode})")
            if init_result.stderr.strip():
                typer.echo(init_result.stderr.strip())
    elif init_script.exists():
        typer.echo(f"{step_prefix}init-worktree.sh exists but is not executable, skipping.")
    else:
        typer.echo(f"{step_prefix}No init-worktree.sh found, skipping dependency refresh.")


def peasant_session_name(ticket_id: str) -> str:
    """Return the canonical session name for a peasant working on *ticket_id*."""
    return f"peasant-{ticket_id}"


def peasant_thread_id(ticket_id: str) -> str:
    """Return the canonical thread ID for a peasant work thread."""
    return f"{ticket_id}-work"


def is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def not_implemented(command: str) -> None:
    print_error(f"{command}: not implemented yet.")
    raise typer.Exit(code=1)


def require_project_root() -> Path:
    """Find the project root or exit with a clear error."""
    try:
        return find_project_root()
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None


def is_git_repo(base: Path) -> bool:
    """Check if base is inside a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=base,
    )
    return result.returncode == 0


def ensure_feature_branch(feature: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to read git branch")

    current = result.stdout.strip()
    if current == feature:
        return

    if current in {"main", "master"}:
        checkout = subprocess.run(["git", "checkout", "-b", feature], text=True)
        if checkout.returncode != 0:
            raise RuntimeError(f"Failed to create branch '{feature}'")
        typer.echo(f"Created branch {feature}")
        return

    typer.echo(f"Warning: current branch '{current}' does not match feature '{feature}'.")


def is_branch_done(branch_dir: Path) -> bool:
    """Check if a branch directory has status 'done' in its state.json."""
    state_path = branch_dir / "state.json"
    if state_path.exists():
        state = read_json(state_path)
        return state.get("status") == "done"
    return False


def install_skill() -> None:
    """Install the bundled kingdom skill to ~/.claude/skills/kingdom/.

    Copies SKILL.md and reference files from the package into the Claude
    skills directory.  Skips if the target is a symlink (dev setup).
    Warns and continues on permission or filesystem errors.
    """
    from importlib.resources import as_file, files

    try:
        target = Path.home() / ".claude" / "skills" / "kingdom"

        # Don't overwrite a dev symlink
        if target.is_symlink():
            return

        skill_pkg = files("kingdom.skill")

        target.mkdir(parents=True, exist_ok=True)
        with as_file(skill_pkg / "SKILL.md") as src:
            (target / "SKILL.md").write_bytes(src.read_bytes())

        refs_target = target / "references"
        refs_target.mkdir(exist_ok=True)
        refs_pkg = skill_pkg / "references"
        for name in ("council.md", "peasants.md", "tickets.md"):
            with as_file(refs_pkg / name) as src:
                (refs_target / name).write_bytes(src.read_bytes())
    except (OSError, RuntimeError) as exc:
        typer.echo(f"Warning: could not install skill ({exc})")
