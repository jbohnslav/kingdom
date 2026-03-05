"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from kingdom.council import Council, create_council  # noqa: F401 (Council used by tests)
from kingdom.design import ensure_design_initialized
from kingdom.state import (
    branch_root,
    clear_current_run,
    ensure_base_layout,
    ensure_branch_layout,
    find_project_root,
    get_current_git_branch,
    normalize_branch_name,
    read_json,
    resolve_current_run,
    set_current_run,
    state_root,
    write_json,
)
from kingdom.ticket import Ticket, list_tickets
from kingdom.worktree import create_worktree, remove_worktree, worktree_path_for  # noqa: F401

from .config import check_cli, check_config, config_app, get_doctor_checks
from .council import council_app
from .design import design_app, get_branch_paths, get_doc_status  # noqa: F401 (re-export)
from .display import error_console, print_error, styled_echo
from .helpers import install_skill, is_git_repo, require_project_root, verbose_echo  # noqa: F401
from .hook import hook_app
from .peasant import (  # noqa: F401
    PeasantContext,
    launch_work_background,
    launch_work_tmux,
    peasant_app,
    resolve_peasant_context,
)
from .plugin import plugin_app
from .ticket import format_ticket_line, format_ticket_summary, get_tickets_dir, ticket_app  # noqa: F401

NO_COLOR = "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="kd",
    help="Kingdom CLI.",
    add_completion=False,
)


@app.callback()
def app_callback(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Print debug output.")] = False,
) -> None:
    ctx.ensure_object(dict)["verbose"] = verbose


# ---------------------------------------------------------------------------
# Sub-app mounting
# ---------------------------------------------------------------------------

app.add_typer(council_app, name="council")
app.add_typer(design_app, name="design")
app.add_typer(peasant_app, name="peasant")
app.add_typer(config_app, name="config")
app.add_typer(hook_app, name="hook")
app.add_typer(plugin_app, name="plugin")
app.add_typer(ticket_app, name="ticket")
app.add_typer(ticket_app, name="tk", hidden=True)  # Alias for muscle memory


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@app.command(help="Initialize a branch-based session and state.")
def start(
    branch: Annotated[str | None, typer.Argument(help="Branch name (defaults to current git branch).")] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force start even if a session is already active.")
    ] = False,
) -> None:
    # If KD_BASE is explicitly set, require it to be valid — no auto-init fallback.
    # Otherwise, fall back to cwd so auto-init can create .kd/ in a fresh repo.
    if os.environ.get("KD_BASE"):
        base = require_project_root()
    else:
        try:
            base = find_project_root()
        except ValueError:
            base = Path.cwd()

    # Auto-init if .kd/ doesn't exist (with git check)
    if not state_root(base).exists():
        if not is_git_repo(base):
            print_error("Not a git repository. Initialize a git repo first, then run `kd start`.")
            raise typer.Exit(code=1)
        # Always auto-init at the git root, not wherever cwd happens to be
        try:
            git_root_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                cwd=base,
                timeout=5,
            )
            if git_root_result.returncode == 0 and git_root_result.stdout.strip():
                base = Path(git_root_result.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # Fall back to using base as-is
        typer.echo("Auto-initializing .kd/ directory...")
        ensure_base_layout(base)

    # Always refresh bundled skill (skips symlinks for dev setups)
    install_skill()

    # Check for existing current run
    current_path = state_root(base) / "current"
    if current_path.exists() and not force:
        existing = current_path.read_text(encoding="utf-8").strip()
        print_error(f"A session is already active: {existing}")
        error_console.print(
            "  If that branch is finished, run `kd done` to clean it up before starting a new session.\n"
            "  If you need to switch mid-work, use `kd start --force` to override."
        )
        raise typer.Exit(code=1)

    # Determine branch name
    if branch is None:
        branch = get_current_git_branch()
        if branch is None:
            print_error("Detached HEAD state. Please provide a branch name:")
            error_console.print("  kd start <branch-name>")
            raise typer.Exit(code=1)

    # Normalize branch name for directory
    normalized = normalize_branch_name(branch)

    # Create branch layout
    branch_dir = ensure_branch_layout(base, branch)

    # Initialize design doc with template
    design_path = branch_dir / "design.md"
    ensure_design_initialized(design_path, branch)

    # Write .kd/current with normalized name
    set_current_run(base, normalized)

    # Update state.json with original branch name
    state_path = branch_dir / "state.json"
    state = read_json(state_path)
    state["branch"] = branch
    write_json(state_path, state)

    typer.echo(f"Started session for branch {branch}")
    typer.echo(f"  Location: {branch_dir}")
    typer.echo(f"  Design: {design_path}")


@app.command(help="Switch the active kd session to another branch.")
def switch(
    branch: Annotated[str | None, typer.Argument(help="Branch name to switch to.")] = None,
) -> None:
    """Switch the active kd session without changing git branch.

    With an argument: validate the branch exists in .kd/branches/ and update .kd/current.
    Without arguments: list all tracked branches, marking the current session and git branch.
    """
    base = require_project_root()
    console = Console()

    if branch is None:
        # List mode: show all tracked branches
        branches_dir = base / ".kd" / "branches"
        if not branches_dir.exists() or not any(branches_dir.iterdir()):
            typer.echo("No tracked branches. Use `kd start <branch>` to create one.")
            return

        # Determine current kd session
        current_session: str | None = None
        current_path = base / ".kd" / "current"
        if current_path.exists():
            current_session = current_path.read_text(encoding="utf-8").strip() or None

        # Determine current git branch
        git_branch = get_current_git_branch()
        git_normalized = normalize_branch_name(git_branch) if git_branch else None

        for branch_dir in sorted(branches_dir.iterdir()):
            if not branch_dir.is_dir():
                continue
            name = branch_dir.name

            # Read original branch name from state.json
            state_path = branch_dir / "state.json"
            original = name
            branch_status = ""
            if state_path.exists():
                try:
                    state = read_json(state_path)
                    original = state.get("branch", name)
                    if state.get("status") == "done":
                        branch_status = " [dim](done)[/dim]"
                except (FileNotFoundError, KeyError):
                    pass

            # Count open tickets
            tickets_dir = branch_dir / "tickets"
            ticket_count = 0
            if tickets_dir.exists():
                ticket_count = sum(1 for f in tickets_dir.glob("*.md"))

            # Build markers
            markers = []
            if name == current_session:
                markers.append("[bold cyan]* session[/bold cyan]")
            if name == git_normalized:
                markers.append("[green]* git[/green]")
            marker_str = f"  ({', '.join(markers)})" if markers else ""

            console.print(f"  {original}{branch_status}  [{ticket_count} tickets]{marker_str}")
        return

    # Switch mode: validate and update
    normalized = normalize_branch_name(branch)
    branch_dir = base / ".kd" / "branches" / normalized
    if not branch_dir.exists():
        print_error(f"Branch '{branch}' not found in .kd/branches/.")
        error_console.print("Available branches:")
        branches_dir = base / ".kd" / "branches"
        if branches_dir.exists():
            for d in sorted(branches_dir.iterdir()):
                if d.is_dir():
                    error_console.print(f"  {d.name}")
        raise typer.Exit(code=1)

    set_current_run(base, normalized)

    # Print summary
    state_path = branch_dir / "state.json"
    original = branch
    if state_path.exists():
        try:
            state = read_json(state_path)
            original = state.get("branch", branch)
        except (FileNotFoundError, KeyError):
            pass

    tickets_dir = branch_dir / "tickets"
    tickets = list_tickets(tickets_dir) if tickets_dir.exists() else []
    open_count = sum(1 for t in tickets if t.status != "closed")
    closed_count = sum(1 for t in tickets if t.status == "closed")

    git_branch = get_current_git_branch()
    git_info = f"  git: {git_branch}" if git_branch else ""
    if git_branch and normalize_branch_name(git_branch) != normalized:
        git_info += " [yellow](mismatch)[/yellow]"

    console.print(f"Switched to [bold]{original}[/bold]")
    console.print(f"  {open_count} open, {closed_count} closed tickets{git_info}")


@app.command(help="Mark the current session as done.")
def done(
    feature: Annotated[str | None, typer.Argument(help="Branch name (defaults to current session).")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Close even if open tickets remain.")] = False,
) -> None:
    """Mark a session as done (status transition only, no file moves)."""
    from datetime import UTC, datetime

    base = require_project_root()

    # Resolve feature: use argument or fall back to current session
    if feature is None:
        try:
            feature = resolve_current_run(base)
        except RuntimeError:
            print_error("No active session. Pass the branch name: `kd done <branch>`")
            raise typer.Exit(code=1) from None

    # Get the branch directory (normalized name)
    normalized = normalize_branch_name(feature)
    source_dir = branch_root(base, feature)

    # Check if it exists
    if not source_dir.exists():
        print_error(f"Branch '{feature}' not found.")
        raise typer.Exit(code=1)

    # Check for open tickets
    if not force:
        tickets_dir = source_dir / "tickets"
        open_tickets = [t for t in list_tickets(tickets_dir) if t.status != "closed"]
        if open_tickets:
            print_error(f"{len(open_tickets)} open ticket(s) on '{feature}':")
            for t in open_tickets:
                error_console.print(f"  {t.id} \\[{t.status}] {t.title}")
            error_console.print("\nClose tickets, move them to backlog with `kd tk move`, or use --force.")
            raise typer.Exit(code=1)

    # Update state.json with status and timestamp
    state_path = source_dir / "state.json"
    if state_path.exists():
        state = read_json(state_path)
    else:
        state = {}
    state["status"] = "done"
    state["done_at"] = datetime.now(UTC).isoformat()
    write_json(state_path, state)

    # Clean up associated worktrees (read from state.json worktrees map)
    worktrees = state.get("worktrees", {})
    if worktrees:
        if not force:
            names = ", ".join(worktrees.keys())
            typer.confirm(f"Remove {len(worktrees)} worktree(s) ({names})?", abort=True)
        for ticket_id, wt_path in worktrees.items():
            wt = Path(wt_path)
            if wt.exists():
                result = subprocess.run(
                    ["git", "worktree", "remove", "--force", str(wt)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    typer.echo(f"Warning: Failed to remove worktree {ticket_id}: {result.stderr.strip()}")
        state["worktrees"] = {}
        write_json(state_path, state)

    # Clear current session pointer (only if this was the current session)
    current_path = state_root(base) / "current"
    session_cleared = False
    if current_path.exists():
        current_feature = current_path.read_text(encoding="utf-8").strip()
        if current_feature == normalized:
            clear_current_run(base)
            session_cleared = True

    # Summary
    tickets_dir = source_dir / "tickets"
    all_tickets = list_tickets(tickets_dir)
    closed_count = sum(1 for t in all_tickets if t.status == "closed")

    console = Console()

    lines: list[str] = []
    if closed_count:
        lines.append(f"[cyan]{closed_count}[/cyan] tickets closed")
    if session_cleared:
        lines.append("Session cleared")

    push_reminder = ""
    try:
        rev_result = subprocess.run(
            ["git", "rev-list", "--count", "@{u}..HEAD"],
            capture_output=True,
            text=True,
        )
        if rev_result.returncode == 0:
            ahead = int(rev_result.stdout.strip())
            if ahead > 0:
                push_reminder = f"[yellow]{ahead} unpushed commit(s) — remember to push[/yellow]"
        else:
            push_reminder = "[yellow]No upstream branch — remember to push[/yellow]"
    except (subprocess.SubprocessError, ValueError) as exc:
        push_reminder = f"[yellow]Could not check upstream status: {exc}[/yellow]"

    if push_reminder:
        lines.append(push_reminder)

    body = "\n".join(lines) if lines else "[dim]No additional info[/dim]"
    panel = Panel(body, title=f"[bold green]Done: {feature}[/bold green]", border_style="green")
    console.print(panel)


@app.command(help="Show current branch, design doc status, and breakdown status.")
def status(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON for machine consumption.")] = False,
) -> None:
    base = require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    normalized = normalize_branch_name(feature)
    bdir = branch_root(base, feature)
    state_path = bdir / "state.json"
    design_path = bdir / "design.md"
    breakdown_path = bdir / "breakdown.md"

    # Read state to get original branch name
    if state_path.exists():
        state = read_json(state_path)
    else:
        state = {}

    # Original branch name (stored in state.json) vs normalized directory name
    original_branch = state.get("branch", feature)

    # Get design and breakdown status
    design_status = get_doc_status(design_path)
    breakdown_status = get_doc_status(breakdown_path)

    # Get design doc path relative to base for display
    design_path_str = str(design_path.relative_to(base)) if design_path.exists() else None

    # Get ticket counts
    tickets_dir = get_tickets_dir(base)
    tickets = list_tickets(tickets_dir) if tickets_dir.exists() else []

    # Count by status
    status_counts = {"open": 0, "in_progress": 0, "in_review": 0, "closed": 0}
    for ticket in tickets:
        if ticket.status in status_counts:
            status_counts[ticket.status] += 1

    # Count ready tickets (open/in_progress with all deps closed — excludes in_review)
    status_by_id = {t.id: t.status for t in tickets}
    ready_count = 0
    for ticket in tickets:
        if ticket.status not in ("open", "in_progress"):
            continue
        all_deps_closed = all(status_by_id.get(dep, "unknown") == "closed" for dep in ticket.deps)
        if all_deps_closed:
            ready_count += 1

    # Design approved status
    design_approved = state.get("design_approved", False)

    # Build output structure
    output = {
        "branch": original_branch,
        "normalized_branch": normalized,
        "design_path": design_path_str,
        "design_status": design_status,
        "design_approved": design_approved,
        "breakdown_status": breakdown_status,
        "tickets": status_counts,
        "ready_count": ready_count,
    }

    # Group tickets by assignee
    role = os.environ.get("KD_ROLE", "")
    agent_name = os.environ.get("KD_AGENT_NAME", "")
    if not role:
        role = "hand" if os.environ.get("CLAUDECODE") else "king"

    assigned: dict[str, list[Ticket]] = {}
    for ticket in tickets:
        if ticket.assignee:
            assigned.setdefault(ticket.assignee, []).append(ticket)

    output["role"] = role
    output["agent_name"] = agent_name
    output["assignments"] = {k: [t.id for t in v] for k, v in assigned.items()}

    if output_json:
        typer.echo(json.dumps(output, indent=2))
    else:
        # Human-readable output
        typer.echo(f"Branch: {original_branch}")
        if design_path_str:
            approved_str = " (approved)" if design_approved else ""
            typer.echo(f"Design: {design_path_str}{approved_str}")
        typer.echo()
        total = sum(status_counts.values())
        typer.echo(
            f"Tickets: {status_counts['open']} open, {status_counts['in_progress']} in progress, "
            f"{status_counts['in_review']} in review, {status_counts['closed']} closed, "
            f"{ready_count} ready ({total} total)"
        )

        if assigned:
            typer.echo()
            typer.echo("Assignments:")
            for assignee, assignee_tickets in assigned.items():
                for t in assignee_tickets:
                    typer.echo(f"  {assignee}: {t.id} [{t.status}] {t.title}")


@app.command(help="Upgrade the CLI and refresh skill files.")
def update() -> None:
    """Run ``uv tool upgrade kingdom-cli`` then refresh Claude skill files."""
    console = Console()

    # Step 1: uv tool upgrade kingdom-cli
    typer.echo("Upgrading kingdom-cli...")
    try:
        result = subprocess.run(
            ["uv", "tool", "upgrade", "kingdom-cli"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        upgrade_ok = result.returncode == 0
        upgrade_output = result.stdout.strip() or result.stderr.strip()
    except FileNotFoundError:
        upgrade_ok = False
        upgrade_output = "uv not found — install it first (https://docs.astral.sh/uv/)"
    except subprocess.TimeoutExpired:
        upgrade_ok = False
        upgrade_output = "uv tool upgrade timed out"

    if upgrade_ok:
        styled_echo(f"  ✓ {upgrade_output or 'already up to date'}", fg=typer.colors.GREEN)
    else:
        styled_echo(f"  ✗ {upgrade_output}", fg=typer.colors.RED)

    # Step 2: refresh skill files
    typer.echo("Refreshing skill files...")
    skill_target = Path.home() / ".claude" / "skills" / "kingdom"
    if skill_target.is_symlink():
        styled_echo("  ○ Skipped (dev symlink)", fg=typer.colors.YELLOW)
        skill_status = "skipped (dev symlink)"
    else:
        if install_skill():
            styled_echo("  ✓ Skill files refreshed", fg=typer.colors.GREEN)
            skill_status = "refreshed"
        else:
            styled_echo("  ✗ Skill refresh failed (see warning above)", fg=typer.colors.RED)
            skill_status = "failed"

    # Summary
    typer.echo()
    upgrade_summary = "upgraded" if upgrade_ok else "failed"
    console.print(
        Panel(
            f"CLI: {upgrade_summary}  |  Skills: {skill_status}",
            title="[bold]kd update[/bold]",
            border_style="green" if upgrade_ok else "yellow",
        )
    )

    if not upgrade_ok or skill_status == "failed":
        raise typer.Exit(code=1)


@app.command(help="Check config and agent CLIs.")
def doctor(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Validate config and verify agent CLIs are installed."""
    from kingdom.state import state_root as _state_root

    base = require_project_root()
    has_issues = False

    # 1. Config validation
    config_path = _state_root(base) / "config.json"
    config_ok, config_error = check_config(base)

    if not config_ok:
        has_issues = True

    if output_json:
        config_result = {"exists": config_path.exists(), "valid": config_ok, "error": config_error}
    else:
        typer.echo("\nConfig:")
        if not config_path.exists():
            styled_echo("  ○ No config.json (using defaults)", fg=typer.colors.YELLOW)
        elif config_ok:
            styled_echo("  ✓ config.json valid", fg=typer.colors.GREEN)
        else:
            styled_echo(f"  ✗ config.json: {config_error}", fg=typer.colors.RED)

    # 2. Agent CLI checks (skip if config is invalid — can't resolve agents)
    cli_results: dict[str, dict[str, bool | str | None]] = {}
    cli_issues: list[dict[str, str]] = []

    if config_ok:
        doctor_checks = get_doctor_checks(base)
        for check in doctor_checks:
            installed, error = check_cli(check["command"])
            cli_results[check["name"]] = {"installed": installed, "error": error}
            if not installed:
                cli_issues.append({"name": check["name"], "hint": check["install_hint"]})

    if output_json:
        console = Console()
        console.print_json(json.dumps({"config": config_result, "agents": cli_results}, indent=2))
    else:
        if not config_ok:
            typer.echo("\nAgent CLIs:")
            styled_echo("  ○ Skipped (fix config first)", fg=typer.colors.YELLOW)
        else:
            typer.echo("\nAgent CLIs:")
            for check in doctor_checks:
                name = check["name"]
                result = cli_results[name]
                if result["installed"]:
                    styled_echo(f"  ✓ {name:12} (installed)", fg=typer.colors.GREEN)
                else:
                    styled_echo(f"  ✗ {name:12} (not found)", fg=typer.colors.RED)

            if cli_issues:
                typer.echo("\nIssues found:")
                for issue in cli_issues:
                    typer.echo(f"  {issue['name']}: {issue['hint']}")
        typer.echo()

    if has_issues or cli_issues:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
