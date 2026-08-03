"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from kingdom.codex_plugin import codex_plugin_install_detected, install_codex_plugin, package_version
from kingdom.council import Council, create_council  # noqa: F401 (Council used by tests)
from kingdom.doctor import binding_issues, context_issues, host_install_issues, resolution_issues, ticket_issues
from kingdom.state import (
    ProjectRootNotFoundError,
    branch_root,
    clear_current_run,
    compact_context_id,
    ensure_base_layout,
    ensure_branch_layout,
    find_project_root,
    get_current_git_branch,
    list_execution_contexts,
    normalize_branch_name,
    parse_context_last_seen,
    prune_stale_execution_contexts,
    read_json,
    resolve_current_run,
    set_current_run,
    state_root,
    write_json,
)
from kingdom.ticket import (
    TICKET_RESOLUTIONS,
    Ticket,
    collect_all_tickets,
    effective_close_reason,
    effective_resolution,
    filter_tickets_by_deps,
    list_tickets,
    validate_terminal_evidence,
)
from kingdom.worktree import create_worktree, remove_worktree, worktree_path_for  # noqa: F401

from .config import check_agent_model, check_cli, check_config, config_app, get_doctor_checks
from .council import council_app
from .design import design_app, get_branch_paths, get_doc_status  # noqa: F401 (re-export)
from .display import error_console, print_error, styled_echo
from .helpers import install_skill, is_git_repo, require_project_root, verbose_echo  # noqa: F401
from .hook import hook_app
from .lord import lord_app
from .peasant import (  # noqa: F401
    PeasantContext,
    launch_work_background,
    launch_work_tmux,
    peasant_app,
    resolve_peasant_context,
)
from .plugin import activate_codex_plugin, plugin_app
from .ticket import format_ticket_line, format_ticket_summary, get_tickets_dir, ticket_app  # noqa: F401

NO_COLOR = "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="kd",
    help="Ticket-first development with durable Markdown worklogs and per-agent execution contexts.",
    epilog=(
        "Core loop: create/find → pull/start → log/close. Organize related work under epics.\n\n"
        "Concurrent example: one agent context can own ticket ab12 while another owns cd34; "
        "`kd tk current` reports only the calling session's ticket.\n\n"
        "Power tools: TUI/council, reviewed peasants, and lords add collaboration and autonomy. "
        "Design docs are optional through `kd design`."
    ),
    add_completion=False,
)


def development_checkout(cwd: Path) -> Path | None:
    """Find the Kingdom source checkout containing cwd, if any."""
    cwd = cwd.resolve()
    for root in (cwd, *cwd.parents):
        manifest = root / "pyproject.toml"
        cli_source = root / "src" / "kingdom" / "cli" / "__init__.py"
        if manifest.is_file() and cli_source.is_file():
            return root
    return None


def development_source_warning(cwd: Path, loaded_module: Path) -> str | None:
    """Explain when kd is not running from the Kingdom checkout containing cwd."""
    checkout = development_checkout(cwd)
    if checkout is None:
        return None

    expected_source = (checkout / "src" / "kingdom").resolve()
    if loaded_module.resolve().is_relative_to(expected_source):
        return None

    return "Warning: kd is not running from this Kingdom checkout. Use `uv run kd ...` to exercise working-tree code."


def version_callback(value: bool) -> None:
    """Print the installed Kingdom CLI version and exit."""
    if value:
        typer.echo(f"kd {package_version()}")
        raise typer.Exit()


@app.callback()
def app_callback(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Print debug output.")] = False,
    show_version: Annotated[
        bool,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show the Kingdom CLI version."),
    ] = False,
) -> None:
    warning = development_source_warning(Path.cwd(), Path(__file__))
    if warning:
        typer.echo(warning, err=True)
    ctx.ensure_object(dict)["verbose"] = verbose


# ---------------------------------------------------------------------------
# Sub-app mounting
# ---------------------------------------------------------------------------

app.add_typer(council_app, name="council")
app.add_typer(design_app, name="design", hidden=True)
app.add_typer(peasant_app, name="peasant")
app.add_typer(config_app, name="config")
app.add_typer(hook_app, name="hook", hidden=True)
app.add_typer(lord_app, name="lord")
app.add_typer(plugin_app, name="plugin")
app.add_typer(ticket_app, name="ticket")
app.add_typer(ticket_app, name="tk", hidden=True)  # Alias for muscle memory


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@app.command(
    help="Initialize or resume a branch workspace. The repository default branch does not limit execution contexts."
)
def start(
    branch: Annotated[str | None, typer.Argument(help="Branch name (defaults to current git branch).")] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Accepted for compatibility; start is already idempotent.")
    ] = False,
) -> None:
    # If KD_BASE is explicitly set, require it to be valid — no auto-init fallback.
    # Otherwise, fall back to cwd so auto-init can create .kd/ in a fresh repo.
    if os.environ.get("KD_BASE"):
        base = require_project_root()
    else:
        try:
            base = find_project_root()
        except ProjectRootNotFoundError:
            base = Path.cwd()
        except ValueError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from None

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
        install_skill()

    # Determine branch name
    if branch is None:
        branch = get_current_git_branch()
        if branch is None:
            print_error("Detached HEAD state. Please provide a branch name:")
            error_console.print("  kd start <branch-name>")
            raise typer.Exit(code=1)

    # Normalize branch name for directory
    normalized = normalize_branch_name(branch)

    # Create or resume branch layout
    branch_existed = branch_root(base, branch).exists()
    branch_dir = ensure_branch_layout(base, branch)

    # .kd/current is the repository's fallback branch, not execution-context identity.
    set_current_run(base, normalized)

    # Update state.json with original branch name
    state_path = branch_dir / "state.json"
    state = read_json(state_path)
    state["branch"] = branch
    write_json(state_path, state)

    branch_tickets = list_tickets(branch_dir / "tickets")
    backlog_tickets = list_tickets(state_root(base) / "backlog" / "tickets")
    all_known_tickets = collect_all_tickets(base, include_done=True)
    ticket_status = {ticket.id: ticket.status for ticket in all_known_tickets}
    visible_branch_tickets = [ticket for ticket in branch_tickets if ticket.status != "closed"]
    has_ready = bool(filter_tickets_by_deps(visible_branch_tickets, ticket_status, ready=True))
    has_active = any(ticket.status in {"in_progress", "in_review"} for ticket in branch_tickets)
    has_blocked = bool(filter_tickets_by_deps(visible_branch_tickets, ticket_status, blocked=True))

    action = "Resumed" if branch_existed else "Started"
    typer.echo(f"{action} workspace for branch {branch}")
    typer.echo(f"  Location: {branch_dir}")
    typer.echo(f"  Tickets: {len(branch_tickets)} branch, {len(backlog_tickets)} backlog")
    if has_ready:
        typer.echo("  Next: kd tk list --ready")
    elif has_active:
        typer.echo("  Next: kd status")
    elif has_blocked:
        typer.echo("  Next: kd tk list --blocked")
    elif backlog_tickets:
        typer.echo("  Next: kd tk list --backlog, then kd tk pull <id>")
    else:
        typer.echo('  Next: kd tk create "<title>" (use --type epic for larger work)')


@app.command(help="Change the repository's default kd branch.")
def switch(
    branch: Annotated[str | None, typer.Argument(help="Branch name to switch to.")] = None,
) -> None:
    """Change the fallback branch without changing Git or execution-context bindings.

    With an argument: validate the branch exists in .kd/branches/ and update .kd/current.
    Without arguments: list all tracked branches, marking the repository default and Git branch.
    """
    base = require_project_root()
    console = Console()

    if branch is None:
        # List mode: show all tracked branches
        branches_dir = base / ".kd" / "branches"
        if not branches_dir.exists() or not any(branches_dir.iterdir()):
            typer.echo("No tracked branches. Use `kd start <branch>` to create one.")
            return

        # Determine repository default branch
        current_default: str | None = None
        current_path = base / ".kd" / "current"
        if current_path.exists():
            current_default = current_path.read_text(encoding="utf-8").strip() or None

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
            if name == current_default:
                markers.append("[bold cyan]* default[/bold cyan]")
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


def terminal_resolution_report(
    tickets: list[Ticket],
) -> tuple[dict[str, int], dict[str, list[dict[str, str | None]]]]:
    """Build the shared human/JSON resolution breakdown for closed tickets."""
    counts = dict.fromkeys(TICKET_RESOLUTIONS, 0)
    outcomes: dict[str, list[dict[str, str | None]]] = {resolution: [] for resolution in TICKET_RESOLUTIONS}
    for ticket in tickets:
        resolution = effective_resolution(ticket)
        if resolution is None:
            continue
        counts[resolution] += 1
        reference = ticket.duplicate_of if resolution == "duplicate" else ticket.superseded_by
        outcomes[resolution].append(
            {
                "id": ticket.id,
                "title": ticket.title,
                "reason": effective_close_reason(ticket),
                "reference": reference,
            }
        )
    return counts, outcomes


@app.command(help="Mark the current session as done.")
def done(
    feature: Annotated[str | None, typer.Argument(help="Branch name (defaults to current session).")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Close even if open tickets remain.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output the completion summary as JSON.")] = False,
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

    tickets_dir = source_dir / "tickets"
    all_tickets = list_tickets(tickets_dir)

    # Check for open tickets
    if not force:
        open_tickets = [ticket for ticket in all_tickets if ticket.status != "closed"]
        if open_tickets:
            print_error(f"{len(open_tickets)} open ticket(s) on '{feature}':")
            for t in open_tickets:
                error_console.print(f"  {t.id} \\[{t.status}] {t.title}")
            error_console.print("\nClose tickets, defer them with `kd tk defer`, or use --force.")
            raise typer.Exit(code=1)

    invalid_tickets = [
        (ticket, errors)
        for ticket in all_tickets
        if ticket.status == "closed" and (errors := validate_terminal_evidence(ticket))
    ]
    if invalid_tickets:
        print_error(f"{len(invalid_tickets)} closed ticket(s) have invalid terminal evidence:")
        for ticket, errors in invalid_tickets:
            for error in errors:
                error_console.print(f"  {ticket.id}: {error}")
        error_console.print("\nFix the ticket closure metadata, or reopen and close the ticket again.")
        raise typer.Exit(code=1)

    closed_tickets = [ticket for ticket in all_tickets if ticket.status == "closed"]
    resolution_counts, outcomes = terminal_resolution_report(closed_tickets)

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
        if not force and sys.stdin.isatty():
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
    closed_count = len(closed_tickets)

    console = Console()

    lines: list[str] = []
    if closed_count:
        lines.append(f"[cyan]{closed_count}[/cyan] tickets closed")
        lines.append("Resolutions:")
        lines.extend(f"  {resolution_counts[resolution]} {resolution}" for resolution in TICKET_RESOLUTIONS)
        for resolution in ("wont-do", "duplicate", "superseded", "invalid"):
            for outcome in outcomes[resolution]:
                reference = f" → {outcome['reference']}" if outcome["reference"] else ""
                reason = f" — {outcome['reason']}" if outcome["reason"] else ""
                lines.append(f"{resolution}: {outcome['id']}{reference}{reason}")
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
                push_reminder = f"{ahead} unpushed commit(s) — remember to push"
        else:
            push_reminder = "No upstream branch — remember to push"
    except (subprocess.SubprocessError, ValueError) as exc:
        push_reminder = f"Could not check upstream status: {exc}"

    if push_reminder:
        lines.append(f"[yellow]{push_reminder}[/yellow]")

    if output_json:
        typer.echo(
            json.dumps(
                {
                    "feature": feature,
                    "status": "done",
                    "done_at": state["done_at"],
                    "tickets_closed": closed_count,
                    "resolutions": resolution_counts,
                    "outcomes": outcomes,
                    "session_cleared": session_cleared,
                    "push_reminder": push_reminder or None,
                },
                indent=2,
            )
        )
        return

    body = "\n".join(lines) if lines else "[dim]No additional info[/dim]"
    panel = Panel(body, title=f"[bold green]Done: {feature}[/bold green]", border_style="green")
    console.print(panel)


@app.command(help="Show ticket progress and concurrent agent contexts for the current branch.")
def status(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON for machine consumption.")] = False,
    stale_hours: Annotated[
        float,
        typer.Option("--stale-hours", min=0.01, help="Hours without activity before a context is stale."),
    ] = 24.0,
    prune_stale: Annotated[
        bool,
        typer.Option("--prune-stale", help="Remove stale runtime context bindings before displaying status."),
    ] = False,
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
    now = datetime.now(UTC)
    stale_after = timedelta(hours=stale_hours)
    pruned_contexts = (
        prune_stale_execution_contexts(base, feature=feature, stale_after=stale_after, now=now) if prune_stale else []
    )
    contexts = list_execution_contexts(base, feature=feature, stale_after=stale_after, now=now)
    tickets_by_id = {ticket.id: ticket for ticket in tickets}
    for context in contexts:
        ticket = tickets_by_id.get(context.get("ticket_id"))
        context["ticket_status"] = ticket.status if ticket else None
        context["ticket_title"] = ticket.title if ticket else None
        context["epic"] = ticket.parent if ticket else None

    # Count by status
    status_counts = {"open": 0, "in_progress": 0, "in_review": 0, "closed": 0}
    for ticket in tickets:
        if ticket.status in status_counts:
            status_counts[ticket.status] += 1

    # Count ready tickets (open with all deps closed — startable, not already started)
    all_known_tickets = collect_all_tickets(base, include_done=True)
    status_by_id = {ticket.id: ticket.status for ticket in all_known_tickets}
    ready_count = len(filter_tickets_by_deps(tickets, status_by_id, ready=True))

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
        "contexts": contexts,
        "pruned_contexts": pruned_contexts,
    }

    # Group tickets by assignee
    role = os.environ.get("KD_ROLE", "")
    agent_name = os.environ.get("KD_AGENT_NAME", "")
    if not role:
        role = "hand" if os.environ.get("CLAUDECODE") else "king"

    assigned: dict[str, list[Ticket]] = {}
    for ticket in tickets:
        if ticket.assignee and ticket.status != "closed":
            assigned.setdefault(ticket.assignee, []).append(ticket)

    output["role"] = role
    output["agent_name"] = agent_name
    output["assignments"] = {k: [t.id for t in v] for k, v in assigned.items()}

    if output_json:
        typer.echo(json.dumps(output, indent=2))
    else:
        # Human-readable output
        typer.echo(f"Branch: {original_branch}")
        typer.echo()
        total = sum(status_counts.values())
        typer.echo(
            f"Tickets: {status_counts['open']} open, {status_counts['in_progress']} in progress, "
            f"{status_counts['in_review']} in review, {status_counts['closed']} closed, "
            f"{ready_count} ready ({total} total)"
        )

        if prune_stale:
            count = len(pruned_contexts)
            noun = "context" if count == 1 else "contexts"
            typer.echo(f"Pruned {count} stale execution {noun}.")

        if contexts:
            typer.echo()
            typer.echo("Contexts (concurrent agent sessions):")
            for context in contexts:
                context_id = compact_context_id(context["context_id"])
                state_labels = []
                if context["stale"]:
                    state_labels.append("stale")
                if not context["active"]:
                    state_labels.append("completed")
                state_label = f" ({', '.join(state_labels)})" if state_labels else ""
                agent_type = f"/{context['agent_type']}" if context.get("agent_type") else ""
                parent = context.get("parent_agent_id")
                parent_label = f" · child of {compact_context_id(parent)}" if isinstance(parent, str) else ""
                ticket_id = context.get("ticket_id") or "—"
                ticket_status = context.get("ticket_status") or "unbound"
                ticket_title = context.get("ticket_title") or ""
                epic = f" · epic {context['epic']}" if context.get("epic") else ""
                last_seen = parse_context_last_seen(context.get("last_seen"))
                seen = last_seen.astimezone().strftime("%Y-%m-%d %H:%M") if last_seen else "unknown"
                typer.echo(
                    f"  {context_id} · {context['host']} · {context['role']}{agent_type}{state_label}{parent_label} · "
                    f"{ticket_id} [{ticket_status}] {ticket_title}{epic} · seen {seen}"
                )

        context_ids = {context["context_id"] for context in contexts}
        other_assignments = {assignee: items for assignee, items in assigned.items() if assignee not in context_ids}
        if other_assignments:
            typer.echo()
            typer.echo("Assignments:")
            for assignee, assignee_tickets in other_assignments.items():
                for t in assignee_tickets:
                    typer.echo(f"  {assignee}: {t.id} [{t.status}] {t.title}")

        if design_path_str:
            approved_str = " (approved)" if design_approved else ""
            typer.echo()
            typer.echo(f"Optional design: {design_path_str}{approved_str}")


@app.command(help="Upgrade the CLI and refresh installed agent integrations.")
def update() -> None:
    """Upgrade the CLI, refresh skills, and update an existing Codex plugin."""
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
    skill_status = install_skill()
    if skill_status == "refreshed":
        styled_echo("  ✓ Skill files refreshed", fg=typer.colors.GREEN)
    elif skill_status == "skipped":
        styled_echo("  ○ Skipped (dev symlink)", fg=typer.colors.YELLOW)
    else:
        styled_echo("  ✗ Skill refresh failed (see warning above)", fg=typer.colors.RED)

    # Step 3: refresh Codex plugin only when the user already configured it.
    plugin_status = "not configured"
    plugin_ok = True
    if codex_plugin_install_detected(Path.home()):
        typer.echo("Refreshing Codex plugin...")
        try:
            plugin_result = install_codex_plugin(Path.home())
            plugin_ok, plugin_message = activate_codex_plugin(plugin_result.marketplace_name)
        except (OSError, RuntimeError, ValueError) as exc:
            plugin_ok = False
            plugin_message = str(exc)
        if plugin_ok:
            plugin_status = plugin_result.status
            styled_echo(f"  ✓ Codex plugin {plugin_status}", fg=typer.colors.GREEN)
        else:
            plugin_status = "failed"
            styled_echo(f"  ✗ {plugin_message}", fg=typer.colors.RED)

    # Summary
    typer.echo()
    upgrade_summary = "upgraded" if upgrade_ok else "failed"
    console.print(
        Panel(
            f"CLI: {upgrade_summary}  |  Skills: {skill_status}  |  Codex plugin: {plugin_status}",
            title="[bold]kd update[/bold]",
            border_style="green" if upgrade_ok else "yellow",
        )
    )

    if not upgrade_ok or skill_status == "failed" or not plugin_ok:
        raise typer.Exit(code=1)


@app.command(help="Check config, agent CLIs, repository state, and host integrations.")
def doctor(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Validate config, runtime state, ticket closures, and host installs."""
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
            model_status, model_error = check_agent_model(check["agent"]) if installed else ("unchecked", None)
            cli_results[check["name"]] = {
                "installed": installed,
                "error": error,
                "model": check["model"],
                "model_source": check["model_source"],
                "effort": check["effort"],
                "model_check": model_status,
                "model_error": model_error,
            }
            if not installed:
                hint = f"{error}. {check['install_hint']}" if error else check["install_hint"]
                cli_issues.append({"name": check["name"], "hint": hint})
            elif model_status == "unavailable":
                cli_issues.append({"name": check["name"], "hint": model_error or "Model unavailable"})

    bindings = binding_issues(base)
    contexts = context_issues(base)
    tickets = ticket_issues(base)
    resolutions = resolution_issues(base)
    host_installs = host_install_issues(base, Path.home())
    state_issues = [*bindings, *contexts, *tickets, *resolutions, *host_installs]
    if state_issues:
        has_issues = True

    if output_json:
        console = Console()
        console.print_json(
            json.dumps(
                {
                    "config": config_result,
                    "agents": cli_results,
                    "bindings": [issue.to_dict() for issue in bindings],
                    "contexts": [issue.to_dict() for issue in contexts],
                    "tickets": [issue.to_dict() for issue in tickets],
                    "resolutions": [issue.to_dict() for issue in resolutions],
                    "host_installs": [issue.to_dict() for issue in host_installs],
                },
                indent=2,
            )
        )
    else:
        if not config_ok:
            typer.echo("\nAgent CLIs:")
            styled_echo("  ○ Skipped (fix config first)", fg=typer.colors.YELLOW)
        else:
            typer.echo("\nAgent CLIs:")
            for check in doctor_checks:
                name = check["name"]
                result = cli_results[name]
                if result["installed"] and result["model_check"] == "unavailable":
                    styled_echo(
                        f"  ✗ {name:12} (installed; {result['model_error']})",
                        fg=typer.colors.RED,
                    )
                elif result["installed"]:
                    model = result["model"]
                    source = result["model_source"]
                    effort = result["effort"]
                    model_check = result["model_check"]
                    styled_echo(
                        f"  ✓ {name:12} (installed; model: {model} [{source}, {model_check}]; effort: {effort})",
                        fg=typer.colors.GREEN,
                    )
                else:
                    styled_echo(f"  ✗ {name:12} ({result['error'] or 'unavailable'})", fg=typer.colors.RED)

            if cli_issues:
                typer.echo("\nIssues found:")
                for issue in cli_issues:
                    typer.echo(f"  {issue['name']}: {issue['hint']}")

        doctor_sections = (
            ("Bindings", bindings),
            ("Contexts", contexts),
            ("Tickets", tickets),
            ("Ticket resolutions", resolutions),
            ("Host integrations", host_installs),
        )
        for title, issues in doctor_sections:
            typer.echo(f"\n{title}:")
            if not issues:
                styled_echo("  ✓ No issues found", fg=typer.colors.GREEN)
                continue
            for issue in issues:
                styled_echo(f"  ✗ [{issue.code}] {issue.message}", fg=typer.colors.RED)
                if issue.path:
                    typer.echo(f"    Path: {issue.path}")
                typer.echo(f"    Repair: {issue.repair}")
        typer.echo("\nDoctor is read-only; no files were changed.")
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
