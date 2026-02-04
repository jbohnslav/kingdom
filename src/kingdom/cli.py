from __future__ import annotations

"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from kingdom.council import Council, create_run_bundle
from kingdom.breakdown import build_breakdown_template, parse_breakdown_tickets
from kingdom.design import build_design_template
from kingdom.state import (
    archive_root,
    backlog_root,
    branch_root,
    branches_root,
    clear_current_run,
    council_logs_root,
    ensure_base_layout,
    ensure_branch_layout,
    logs_root,
    normalize_branch_name,
    read_json,
    resolve_current_run,
    sessions_root,
    set_current_run,
    state_root,
    write_json,
)
from kingdom.ticket import (
    AmbiguousTicketMatch,
    Ticket,
    find_ticket,
    generate_ticket_id,
    list_tickets,
    read_ticket,
    write_ticket,
)

app = typer.Typer(
    name="kd",
    help="Kingdom CLI.",
    add_completion=False,
)


def not_implemented(command: str) -> None:
    typer.echo(f"{command}: not implemented yet.")
    raise typer.Exit(code=1)


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
        typer.echo(f"Created branch: {feature}")
        return

    typer.echo(
        f"Warning: current branch '{current}' does not match feature '{feature}'."
    )


@app.command(help="Initialize .kd/ directory structure.")
def init(
    no_git: Annotated[
        bool, typer.Option("--no-git", help="Skip git repository check.")
    ] = False,
    no_gitignore: Annotated[
        bool, typer.Option("--no-gitignore", help="Skip .gitignore creation.")
    ] = False,
) -> None:
    """Initialize the .kd/ directory structure for Kingdom.

    Idempotent: creates missing pieces, skips existing.
    """
    base = Path.cwd()

    if not no_git and not is_git_repo(base):
        typer.echo("Error: Not a git repository. Use --no-git to initialize anyway.")
        raise typer.Exit(code=1)

    paths = ensure_base_layout(base, create_gitignore=not no_gitignore)
    typer.echo(f"Initialized: {paths['state_root']}")


def get_current_git_branch() -> str | None:
    """Get the current git branch name, or None if detached HEAD."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    # "HEAD" means detached HEAD state
    if branch == "HEAD":
        return None
    return branch


@app.command(help="Initialize a branch-based run and state.")
def start(
    branch: Annotated[
        Optional[str], typer.Argument(help="Branch name (defaults to current git branch).")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force start even if a run is already active.")
    ] = False,
) -> None:
    base = Path.cwd()

    # Auto-init if .kd/ doesn't exist (with git check)
    if not state_root(base).exists():
        if not is_git_repo(base):
            typer.echo("Error: Not a git repository. Run `kd init --no-git` first.")
            raise typer.Exit(code=1)
        typer.echo("Auto-initializing .kd/ directory...")
        ensure_base_layout(base)

    # Check for existing current run
    current_path = state_root(base) / "current"
    if current_path.exists() and not force:
        existing = current_path.read_text(encoding="utf-8").strip()
        typer.echo(f"Error: A run is already active: {existing}")
        typer.echo("Use --force to override, or run `kd done` first.")
        raise typer.Exit(code=1)

    # Determine branch name
    if branch is None:
        branch = get_current_git_branch()
        if branch is None:
            typer.echo("Error: Detached HEAD state. Please provide a branch name:")
            typer.echo("  kd start <branch-name>")
            raise typer.Exit(code=1)

    # Normalize branch name for directory
    normalized = normalize_branch_name(branch)

    # Create branch layout
    branch_dir = ensure_branch_layout(base, branch)

    # Write .kd/current with normalized name
    set_current_run(base, normalized)

    # Update state.json with original branch name
    state_path = branch_dir / "state.json"
    state = read_json(state_path)
    state["branch"] = branch
    write_json(state_path, state)

    typer.echo(f"Started run for branch: {branch}")
    typer.echo(f"Location: {branch_dir}")


@app.command(help="Mark the current run as done and archive it.")
def done(
    feature: Annotated[
        Optional[str], typer.Argument(help="Branch name (defaults to current run).")
    ] = None,
) -> None:
    """Mark a run as complete, archive it, and clear the current run pointer."""
    import shutil
    from datetime import datetime, timezone

    base = Path.cwd()

    # Resolve feature: use argument or fall back to current run
    if feature is None:
        try:
            feature = resolve_current_run(base)
        except RuntimeError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1)

    # Get the branch directory (normalized name)
    normalized = normalize_branch_name(feature)
    source_dir = branch_root(base, feature)

    # Check if it exists in new structure
    if not source_dir.exists():
        # Fall back to legacy runs structure
        legacy_dir = state_root(base) / "runs" / feature
        if legacy_dir.exists():
            source_dir = legacy_dir
        else:
            typer.echo(f"Error: Branch '{feature}' not found.")
            raise typer.Exit(code=1)

    # Update state.json with status and timestamp before moving
    state_path = source_dir / "state.json"
    if state_path.exists():
        state = read_json(state_path)
    else:
        state = {}
    state["status"] = "done"
    state["done_at"] = datetime.now(timezone.utc).isoformat()
    write_json(state_path, state)

    # Determine archive destination
    archive_base = state_root(base) / "archive"
    archive_base.mkdir(parents=True, exist_ok=True)
    archive_dest = archive_base / normalized

    # Handle collision: add timestamp suffix if destination exists
    if archive_dest.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archive_dest = archive_base / f"{normalized}-{timestamp}"

    # Move branch folder to archive
    shutil.move(str(source_dir), str(archive_dest))

    # Clean up associated worktrees
    worktree_dir = state_root(base) / "worktrees" / normalized
    if worktree_dir.exists():
        # Remove git worktree first
        import subprocess
        for worktree in worktree_dir.iterdir():
            if worktree.is_dir():
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    capture_output=True,
                )
        # Remove the parent worktree directory if empty
        try:
            worktree_dir.rmdir()
        except OSError:
            pass  # Not empty, that's fine

    # Clear current run pointer (only if this was the current run)
    current_path = state_root(base) / "current"
    if current_path.exists():
        current_feature = current_path.read_text(encoding="utf-8").strip()
        if current_feature == normalized:
            clear_current_run(base)

    typer.echo(f"Archived '{feature}' to {archive_dest.relative_to(base)}")


council_app = typer.Typer(name="council", help="Query council members.")
app.add_typer(council_app, name="council")


@council_app.command("ask", help="Query all council members and display responses.")
def council_ask(
    prompt: Annotated[str, typer.Argument(help="Prompt to send to council members.")],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output JSON format.")
    ] = False,
    open_dir: Annotated[
        bool, typer.Option("--open", help="Open response directory in $EDITOR.")
    ] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", help="Per-model timeout in seconds.")
    ] = 120,
) -> None:
    """Query all council members and display with Rich panels."""
    base = Path.cwd()
    feature = resolve_current_run(base)

    logs_dir = logs_root(base, feature)
    sessions_dir = sessions_root(base, feature)
    council_logs_dir = council_logs_root(base, feature)

    # Ensure directories exist
    logs_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    council_logs_dir.mkdir(parents=True, exist_ok=True)

    console = Console()

    c = Council.create(logs_dir=logs_dir)
    c.timeout = timeout
    c.load_sessions(sessions_dir)

    # Query with progress
    responses = _query_with_progress(c, prompt, json_output, console)
    c.save_sessions(sessions_dir)

    # Create run bundle
    bundle = create_run_bundle(council_logs_dir, prompt, responses)
    run_id = bundle["run_id"]
    run_dir = bundle["run_dir"]
    response_paths = bundle["paths"]

    if json_output:
        _output_json(responses, run_id, run_dir, response_paths)
    else:
        _display_rich_panels(responses, run_dir, console)

    if open_dir:
        editor = os.environ.get("EDITOR", "open")
        subprocess.run([editor, str(run_dir)])


@council_app.command("reset", help="Clear all council sessions.")
def council_reset() -> None:
    """Clear all council member sessions."""
    base = Path.cwd()
    feature = resolve_current_run(base)

    logs_dir = logs_root(base, feature)
    sessions_dir = sessions_root(base, feature)

    # Ensure directories exist
    logs_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    c = Council.create(logs_dir=logs_dir)
    c.load_sessions(sessions_dir)
    c.reset_sessions()
    c.save_sessions(sessions_dir)
    typer.echo("Sessions cleared.")


def _query_with_progress(council, prompt, json_output, console):
    """Query with spinner showing member progress."""
    if json_output:
        # No spinner for JSON output
        return council.query(prompt)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Querying council members...", total=None)
        responses = council.query(prompt)
        progress.update(task, description="Done")

    return responses


def _display_rich_panels(responses, run_dir, console):
    """Display responses as Rich panels with Markdown."""
    for name in ["claude", "codex", "agent"]:
        response = responses.get(name)
        if not response:
            continue

        if response.error:
            content = f"> **Error:** {response.error}\n\n"
            if response.text:
                content += response.text
            else:
                content += "*No response*"
        else:
            content = response.text if response.text else "*No response*"

        panel = Panel(
            Markdown(content),
            title=response.name,
            border_style="blue",
        )
        console.print(panel)
        console.print(f"[dim]{response.elapsed:.1f}s[/dim]", justify="right")
        console.print()

    console.print(f"[dim]Saved to: {run_dir}[/dim]")


def _output_json(responses, run_id, run_dir, response_paths):
    """Output JSON format for --json flag."""
    output = {
        "run_id": run_id,
        "responses": {
            name: {
                "text": r.text,
                "error": r.error,
                "elapsed": r.elapsed,
            }
            for name, r in responses.items()
        },
        "paths": {
            "run_dir": str(run_dir),
            "responses": {name: str(path) for name, path in response_paths.items()},
        },
    }
    print(json.dumps(output, indent=2))


design_app = typer.Typer(name="design", help="Manage design documents.")
app.add_typer(design_app, name="design")


def _get_branch_paths(base: Path, feature: str) -> tuple[Path, Path, Path, Path]:
    """Get design.md, breakdown.md, state.json paths, preferring branch structure.

    Returns: (branch_dir, design_path, breakdown_path, state_path)
    """
    branch_dir = branch_root(base, feature)
    if branch_dir.exists():
        return (
            branch_dir,
            branch_dir / "design.md",
            branch_dir / "breakdown.md",
            branch_dir / "state.json",
        )
    # Fall back to legacy runs structure
    legacy_dir = state_root(base) / "runs" / feature
    return (
        legacy_dir,
        legacy_dir / "design.md",
        legacy_dir / "breakdown.md",
        legacy_dir / "state.json",
    )


def _get_design_paths(base: Path, feature: str) -> tuple[Path, Path]:
    """Get design.md and state.json paths, preferring branch structure."""
    _, design_path, _, state_path = _get_branch_paths(base, feature)
    return design_path, state_path


@design_app.callback(invoke_without_command=True)
def design_default(ctx: typer.Context) -> None:
    """Draft the design doc (creates template if empty)."""
    if ctx.invoked_subcommand is not None:
        return
    base = Path.cwd()
    feature = resolve_current_run(base)
    design_path, _ = _get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(build_design_template(feature), encoding="utf-8")
        typer.echo(f"Created design template at {design_path}")
        return

    typer.echo(f"Design already exists at {design_path}")


@design_app.command("show", help="Print the design document.")
def design_show() -> None:
    """Print the design.md contents."""
    base = Path.cwd()
    feature = resolve_current_run(base)
    design_path, _ = _get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        typer.echo("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    console = Console()
    console.print(Markdown(design_path.read_text(encoding="utf-8")))


@design_app.command("approve", help="Mark the design as approved.")
def design_approve() -> None:
    """Set design_approved=true in state.json."""
    base = Path.cwd()
    feature = resolve_current_run(base)
    design_path, state_path = _get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        typer.echo("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    state = read_json(state_path) if state_path.exists() else {}
    state["design_approved"] = True
    write_json(state_path, state)
    typer.echo("Design approved.")


@app.command(help="Draft or iterate the current breakdown.")
def breakdown(
    apply: bool = typer.Option(
        False, "--apply", help="Create tickets from breakdown.md."
    ),
) -> None:
    from datetime import datetime, timezone

    base = Path.cwd()
    feature = resolve_current_run(base)
    _, _, breakdown_path, state_path = _get_branch_paths(base, feature)

    if not breakdown_path.exists() or not breakdown_path.read_text(encoding="utf-8").strip():
        breakdown_path.parent.mkdir(parents=True, exist_ok=True)
        breakdown_path.write_text(build_breakdown_template(feature), encoding="utf-8")
        typer.echo(f"Created breakdown template at {breakdown_path}")
        return

    if not apply:
        typer.echo(f"Breakdown already exists at {breakdown_path}")
        typer.echo("Use --apply to create tickets from the breakdown.")
        return

    parsed_tickets = parse_breakdown_tickets(breakdown_path.read_text(encoding="utf-8"))
    if not parsed_tickets:
        raise RuntimeError("No tickets found in breakdown.md")

    # Get tickets directory for current branch
    tickets_dir = _get_tickets_dir(base)
    tickets_dir.mkdir(parents=True, exist_ok=True)

    created: dict[str, str] = {}
    for parsed in parsed_tickets:
        # Build ticket body from description and acceptance criteria
        body_parts = []
        if parsed["description"]:
            body_parts.append(parsed["description"])
        if parsed["acceptance"]:
            body_parts.append("\n## Acceptance Criteria\n")
            for item in parsed["acceptance"]:
                body_parts.append(f"- [ ] {item}")
        body = "\n".join(body_parts) if body_parts else ""

        # Create ticket using internal module
        ticket_id = generate_ticket_id(tickets_dir)
        ticket = Ticket(
            id=ticket_id,
            status="open",
            deps=[],  # Dependencies added in second pass
            links=[],
            created=datetime.now(timezone.utc),
            type="task",
            priority=parsed["priority"],
            title=parsed["title"],
            body=body,
        )

        ticket_path = tickets_dir / f"{ticket_id}.md"
        write_ticket(ticket, ticket_path)
        created[parsed["breakdown_id"]] = ticket_id
        typer.echo(f"Created ticket {ticket_id} for {parsed['breakdown_id']}")

    # Second pass: add dependencies
    for parsed in parsed_tickets:
        ticket_id = created.get(parsed["breakdown_id"])
        if not ticket_id:
            continue
        deps_to_add = []
        for dep in parsed["depends_on"]:
            dep_id = created.get(dep, dep)  # Use mapped ID or original if external
            deps_to_add.append(dep_id)

        if deps_to_add:
            ticket_path = tickets_dir / f"{ticket_id}.md"
            ticket = read_ticket(ticket_path)
            ticket.deps = deps_to_add
            write_ticket(ticket, ticket_path)

    state = read_json(state_path) if state_path.exists() else {}
    state["tickets"] = {**state.get("tickets", {}), **created}
    write_json(state_path, state)


@app.command(help="Create a worktree for working on a ticket.")
def peasant(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID to work on.")],
    clean: Annotated[
        bool, typer.Option("--clean", help="Remove the worktree instead of creating.")
    ] = False,
) -> None:
    """Create or remove a git worktree for ticket development."""
    base = Path.cwd()

    # Find the ticket
    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, _ = result
    full_ticket_id = ticket.id

    # Worktree location
    worktrees_dir = state_root(base) / "worktrees"
    worktree_path = worktrees_dir / full_ticket_id

    if clean:
        # Remove worktree
        if not worktree_path.exists():
            typer.echo(f"No worktree found for {full_ticket_id}")
            raise typer.Exit(code=1)

        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"Error removing worktree: {result.stderr.strip()}")
            raise typer.Exit(code=1)

        # Update state
        try:
            feature = resolve_current_run(base)
            _, state_path = _get_design_paths(base, feature)
            state = read_json(state_path) if state_path.exists() else {}
            worktrees = state.get("worktrees", {})
            worktrees.pop(full_ticket_id, None)
            state["worktrees"] = worktrees
            write_json(state_path, state)
        except RuntimeError:
            pass  # No active run, skip state update

        typer.echo(f"Removed worktree for {full_ticket_id}")
        return

    # Create worktree
    if worktree_path.exists():
        typer.echo(f"Worktree already exists: {worktree_path}")
        typer.echo(f"  cd {worktree_path}")
        return

    worktrees_dir.mkdir(parents=True, exist_ok=True)

    # Create a branch for this ticket
    branch_name = f"ticket/{full_ticket_id}"

    # Check if branch exists
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True,
        text=True,
    )
    branch_exists = result.returncode == 0

    if branch_exists:
        # Use existing branch
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            capture_output=True,
            text=True,
        )
    else:
        # Create new branch from current HEAD
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        typer.echo(f"Error creating worktree: {result.stderr.strip()}")
        raise typer.Exit(code=1)

    # Track in state.json
    try:
        feature = resolve_current_run(base)
        _, state_path = _get_design_paths(base, feature)
        state = read_json(state_path) if state_path.exists() else {}
        worktrees = state.get("worktrees", {})
        worktrees[full_ticket_id] = str(worktree_path)
        state["worktrees"] = worktrees
        write_json(state_path, state)
    except RuntimeError:
        pass  # No active run, skip state update

    typer.echo(f"Created worktree for {full_ticket_id}")
    typer.echo(f"  Branch: {branch_name}")
    typer.echo(f"  Path: {worktree_path}")
    typer.echo()
    typer.echo("To work on this ticket:")
    typer.echo(f"  cd {worktree_path}")
    typer.echo(f"  kd ticket start {full_ticket_id}")
    typer.echo()
    typer.echo("When done:")
    typer.echo(f"  kd ticket close {full_ticket_id}")
    typer.echo(f"  kd peasant {full_ticket_id} --clean")


@app.command(help="Reserved for broader develop phase (MVP stub).")
def dev(ticket: str | None = typer.Argument(None, help="Optional ticket id.")) -> None:
    if ticket:
        typer.echo("MVP uses `kd peasant <ticket>` for single-ticket execution.")
        raise typer.Exit(code=1)
    typer.echo("`kd dev` is reserved. Use `kd peasant <ticket>` in the MVP.")


def _get_doc_status(path: Path) -> str:
    """Get status of a markdown doc: 'empty', 'draft', or path."""
    if not path.exists():
        return "missing"
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return "empty"
    return "present"


@app.command(help="Show current branch, design doc status, and breakdown status.")
def status(
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON for machine consumption.")
    ] = False,
) -> None:
    base = Path.cwd()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    # Try new branch-based structure first, fall back to legacy
    normalized = normalize_branch_name(feature)
    branch_dir = branch_root(base, feature)

    if branch_dir.exists():
        state_path = branch_dir / "state.json"
        design_path = branch_dir / "design.md"
        breakdown_path = branch_dir / "breakdown.md"
    else:
        # Fall back to legacy runs structure
        legacy_dir = state_root(base) / "runs" / feature
        state_path = legacy_dir / "state.json"
        design_path = legacy_dir / "design.md"
        breakdown_path = legacy_dir / "breakdown.md"

    # Read state to get original branch name
    if state_path.exists():
        state = read_json(state_path)
    else:
        state = {}

    # Original branch name (stored in state.json) vs normalized directory name
    original_branch = state.get("branch", feature)

    # Get design and breakdown status
    design_status = _get_doc_status(design_path)
    breakdown_status = _get_doc_status(breakdown_path)

    # Get design doc path relative to base for display
    design_path_str = str(design_path.relative_to(base)) if design_path.exists() else None

    # Get ticket counts
    tickets_dir = _get_tickets_dir(base)
    tickets = list_tickets(tickets_dir) if tickets_dir.exists() else []

    # Count by status
    status_counts = {"open": 0, "in_progress": 0, "closed": 0}
    for ticket in tickets:
        if ticket.status in status_counts:
            status_counts[ticket.status] += 1

    # Count ready tickets (open/in_progress with all deps closed)
    status_by_id = {t.id: t.status for t in tickets}
    ready_count = 0
    for ticket in tickets:
        if ticket.status not in ("open", "in_progress"):
            continue
        all_deps_closed = all(
            status_by_id.get(dep, "unknown") == "closed" for dep in ticket.deps
        )
        if all_deps_closed:
            ready_count += 1

    # Build output structure
    output = {
        "branch": original_branch,
        "normalized_branch": normalized,
        "design_path": design_path_str,
        "design_status": design_status,
        "breakdown_status": breakdown_status,
        "tickets": status_counts,
        "ready_count": ready_count,
    }

    if output_json:
        typer.echo(json.dumps(output, indent=2))
    else:
        # Human-readable output
        typer.echo(f"Branch: {original_branch}")
        if design_path_str:
            typer.echo(f"Design: {design_path_str}")
        typer.echo()
        typer.echo(f"Design: {design_status}")
        typer.echo(f"Breakdown: {breakdown_status}")
        typer.echo()
        total = sum(status_counts.values())
        typer.echo(f"Tickets: {status_counts['open']} open, {status_counts['in_progress']} in progress, {status_counts['closed']} closed ({total} total)")
        typer.echo(f"Ready: {ready_count}")


DOCTOR_CHECKS = [
    {
        "name": "claude",
        "command": ["claude", "--version"],
        "install_hint": "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code",
    },
    {
        "name": "codex",
        "command": ["codex", "--version"],
        "install_hint": "Install Codex CLI: npm install -g @openai/codex",
    },
    {
        "name": "cursor",
        "command": ["cursor", "--version"],
        "install_hint": "Install Cursor: https://cursor.com",
    },
]


def _check_cli(command: list[str]) -> tuple[bool, str | None]:
    """Check if a CLI command is available."""
    try:
        subprocess.run(command, capture_output=True, timeout=5)
        return (True, None)
    except FileNotFoundError:
        return (False, "Command not found")
    except subprocess.TimeoutExpired:
        return (False, "Command timed out")


@app.command(help="Check if council member CLIs are installed.")
def doctor(
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON.")
    ] = False,
) -> None:
    """Verify council member CLIs are installed and provide guidance."""
    results: dict[str, dict[str, bool | str | None]] = {}
    issues: list[dict[str, str]] = []

    for check in DOCTOR_CHECKS:
        installed, error = _check_cli(check["command"])
        results[check["name"]] = {"installed": installed, "error": error}
        if not installed:
            issues.append({"name": check["name"], "hint": check["install_hint"]})

    if output_json:
        print(json.dumps(results, indent=2))
    else:
        console = Console()
        console.print("\nCouncil member CLIs:")
        for check in DOCTOR_CHECKS:
            name = check["name"]
            result = results[name]
            if result["installed"]:
                console.print(f"  [green]✓[/green] {name:12} (installed)")
            else:
                console.print(f"  [red]✗[/red] {name:12} (not found)")

        if issues:
            console.print("\nIssues found:")
            for issue in issues:
                console.print(f"  {issue['name']}: {issue['hint']}")
        console.print()

    if issues:
        raise typer.Exit(code=1)


# Ticket subcommand group
ticket_app = typer.Typer(name="ticket", help="Manage tickets.")
app.add_typer(ticket_app, name="ticket")
app.add_typer(ticket_app, name="tk", hidden=True)  # Alias for muscle memory


def _get_tickets_dir(base: Path, backlog: bool = False) -> Path:
    """Get the tickets directory for the current context."""
    if backlog:
        return backlog_root(base) / "tickets"

    # Try to get current branch's tickets directory
    try:
        feature = resolve_current_run(base)
        normalized = normalize_branch_name(feature)
        branch_dir = branch_root(base, feature)
        if branch_dir.exists():
            return branch_dir / "tickets"
        # Fall back to legacy runs structure
        return state_root(base) / "runs" / feature / "tickets"
    except RuntimeError:
        # No active branch, use backlog
        return backlog_root(base) / "tickets"


@ticket_app.command("create", help="Create a new ticket.")
def ticket_create(
    title: Annotated[str, typer.Argument(help="Ticket title.")],
    description: Annotated[
        Optional[str], typer.Option("-d", "--description", help="Ticket description.")
    ] = None,
    priority: Annotated[
        int, typer.Option("-p", "--priority", help="Priority (1-3, 1 is highest).")
    ] = 2,
    ticket_type: Annotated[
        str, typer.Option("-t", "--type", help="Ticket type (task, bug, feature).")
    ] = "task",
    backlog: Annotated[
        bool, typer.Option("--backlog", help="Create in backlog instead of current branch.")
    ] = False,
) -> None:
    """Create a new ticket in the current branch or backlog."""
    from datetime import datetime, timezone

    base = Path.cwd()

    # Ensure base layout exists
    ensure_base_layout(base)

    tickets_dir = _get_tickets_dir(base, backlog=backlog)
    tickets_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique ID
    ticket_id = generate_ticket_id(tickets_dir)

    # Build body with acceptance criteria section
    body = description or ""
    if not body:
        body = "## Acceptance Criteria\n\n- [ ] "

    # Create ticket
    ticket = Ticket(
        id=ticket_id,
        status="open",
        deps=[],
        links=[],
        created=datetime.now(timezone.utc),
        type=ticket_type,
        priority=priority,
        title=title,
        body=body,
    )

    ticket_path = tickets_dir / f"{ticket_id}.md"
    write_ticket(ticket, ticket_path)

    typer.echo(ticket_id)


@ticket_app.command("list", help="List tickets.")
def ticket_list(
    all_tickets: Annotated[
        bool, typer.Option("--all", "-a", help="List all tickets across all locations.")
    ] = False,
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON.")
    ] = False,
) -> None:
    """List tickets in the current branch or all locations."""
    base = Path.cwd()

    if all_tickets:
        # Collect tickets from all locations
        locations: list[tuple[str, Path]] = []

        # branches/*/tickets/
        branches_dir = branches_root(base)
        if branches_dir.exists():
            for branch_dir in branches_dir.iterdir():
                if branch_dir.is_dir():
                    tickets_dir = branch_dir / "tickets"
                    if tickets_dir.exists():
                        locations.append((f"branch:{branch_dir.name}", tickets_dir))

        # backlog/tickets/
        backlog_tickets = backlog_root(base) / "tickets"
        if backlog_tickets.exists():
            locations.append(("backlog", backlog_tickets))

        # archive/*/tickets/
        archive_dir = archive_root(base)
        if archive_dir.exists():
            for archive_item in archive_dir.iterdir():
                if archive_item.is_dir():
                    tickets_dir = archive_item / "tickets"
                    if tickets_dir.exists():
                        locations.append((f"archive:{archive_item.name}", tickets_dir))

        all_results: list[dict] = []
        for location_name, tickets_dir in locations:
            tickets = list_tickets(tickets_dir)
            for ticket in tickets:
                all_results.append({
                    "id": ticket.id,
                    "priority": ticket.priority,
                    "status": ticket.status,
                    "title": ticket.title,
                    "location": location_name,
                })

        if output_json:
            typer.echo(json.dumps(all_results, indent=2))
        else:
            for item in all_results:
                loc = item["location"]
                typer.echo(f"{item['id']} [P{item['priority']}][{item['status']}] - {item['title']} ({loc})")
    else:
        # List tickets for current branch only
        tickets_dir = _get_tickets_dir(base)
        tickets = list_tickets(tickets_dir)

        if output_json:
            results = [
                {
                    "id": t.id,
                    "priority": t.priority,
                    "status": t.status,
                    "title": t.title,
                }
                for t in tickets
            ]
            typer.echo(json.dumps(results, indent=2))
        else:
            if not tickets:
                typer.echo("No tickets found.")
                return
            for ticket in tickets:
                typer.echo(f"{ticket.id} [P{ticket.priority}][{ticket.status}] - {ticket.title}")


@ticket_app.command("show", help="Show a ticket.")
def ticket_show(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON.")
    ] = False,
) -> None:
    """Display a ticket by ID (supports partial matching)."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    if output_json:
        output = {
            "id": ticket.id,
            "status": ticket.status,
            "priority": ticket.priority,
            "type": ticket.type,
            "title": ticket.title,
            "body": ticket.body,
            "deps": ticket.deps,
            "links": ticket.links,
            "created": ticket.created.isoformat(),
            "assignee": ticket.assignee,
            "path": str(ticket_path),
        }
        typer.echo(json.dumps(output, indent=2))
    else:
        # Read and display the raw file content for human-readable output
        content = ticket_path.read_text(encoding="utf-8")
        console = Console()
        console.print(Markdown(content))


def _update_ticket_status(ticket_id: str, new_status: str) -> None:
    """Helper to update a ticket's status."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    old_status = ticket.status
    ticket.status = new_status
    write_ticket(ticket, ticket_path)
    typer.echo(f"{ticket.id}: {old_status} → {new_status}")


@ticket_app.command("start", help="Mark a ticket as in_progress.")
def ticket_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status to in_progress."""
    _update_ticket_status(ticket_id, "in_progress")


@ticket_app.command("close", help="Mark a ticket as closed.")
def ticket_close(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status to closed."""
    _update_ticket_status(ticket_id, "closed")


@ticket_app.command("reopen", help="Reopen a closed ticket.")
def ticket_reopen(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status back to open."""
    _update_ticket_status(ticket_id, "open")


@ticket_app.command("dep", help="Add a dependency to a ticket.")
def ticket_dep(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    depends_on: Annotated[str, typer.Argument(help="ID of ticket this depends on.")],
) -> None:
    """Add a dependency: ticket_id depends on depends_on."""
    base = Path.cwd()

    # Find both tickets
    try:
        result = find_ticket(base, ticket_id)
        dep_result = find_ticket(base, depends_on)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)
    if dep_result is None:
        typer.echo(f"Dependency ticket not found: {depends_on}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    dep_ticket, _ = dep_result

    # Add dependency if not already present
    if dep_ticket.id not in ticket.deps:
        ticket.deps.append(dep_ticket.id)
        write_ticket(ticket, ticket_path)
        typer.echo(f"{ticket.id} now depends on {dep_ticket.id}")
    else:
        typer.echo(f"{ticket.id} already depends on {dep_ticket.id}")


@ticket_app.command("undep", help="Remove a dependency from a ticket.")
def ticket_undep(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    depends_on: Annotated[str, typer.Argument(help="ID of dependency to remove.")],
) -> None:
    """Remove a dependency from a ticket."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    # Find the full ID of the dependency to remove
    matching_deps = [d for d in ticket.deps if depends_on in d]
    if not matching_deps:
        typer.echo(f"{ticket.id} does not depend on {depends_on}")
        raise typer.Exit(code=1)

    for dep_id in matching_deps:
        ticket.deps.remove(dep_id)
        typer.echo(f"Removed dependency {ticket.id} → {dep_id}")

    write_ticket(ticket, ticket_path)


@ticket_app.command("move", help="Move a ticket to another branch.")
def ticket_move(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    target: Annotated[str, typer.Argument(help="Target branch name or 'backlog'.")],
) -> None:
    """Move a ticket to a different branch or backlog."""
    from kingdom.ticket import move_ticket

    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    # Determine destination
    if target.lower() == "backlog":
        dest_dir = backlog_root(base) / "tickets"
    else:
        normalized = normalize_branch_name(target)
        dest_dir = branches_root(base) / normalized / "tickets"

    dest_dir.mkdir(parents=True, exist_ok=True)
    new_path = move_ticket(ticket_path, dest_dir)
    typer.echo(f"Moved {ticket.id} to {new_path.parent.parent.name}")


@ticket_app.command("ready", help="List tickets ready to work on.")
def ticket_ready(
    output_json: Annotated[
        bool, typer.Option("--json", help="Output as JSON.")
    ] = False,
) -> None:
    """List open tickets with no open dependencies."""
    base = Path.cwd()

    # Collect all tickets to build status lookup
    all_tickets: list[tuple[Ticket, str]] = []  # (ticket, location)

    # branches/*/tickets/
    branches_dir = branches_root(base)
    if branches_dir.exists():
        for branch_dir in branches_dir.iterdir():
            if branch_dir.is_dir():
                tickets_dir = branch_dir / "tickets"
                if tickets_dir.exists():
                    for t in list_tickets(tickets_dir):
                        all_tickets.append((t, f"branch:{branch_dir.name}"))

    # backlog/tickets/
    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        for t in list_tickets(backlog_tickets):
            all_tickets.append((t, "backlog"))

    # Build status lookup for dependency checking
    status_by_id = {t.id: t.status for t, _ in all_tickets}

    # Filter: open tickets with no open dependencies
    ready_tickets = []
    for ticket, location in all_tickets:
        if ticket.status not in ("open", "in_progress"):
            continue
        # Check if all dependencies are closed
        has_open_dep = False
        for dep_id in ticket.deps:
            dep_status = status_by_id.get(dep_id, "unknown")
            if dep_status != "closed":
                has_open_dep = True
                break
        if not has_open_dep:
            ready_tickets.append((ticket, location))

    if output_json:
        results = [
            {
                "id": t.id,
                "priority": t.priority,
                "status": t.status,
                "title": t.title,
                "location": loc,
            }
            for t, loc in ready_tickets
        ]
        typer.echo(json.dumps(results, indent=2))
    else:
        if not ready_tickets:
            typer.echo("No ready tickets.")
            return
        for ticket, _ in ready_tickets:
            typer.echo(f"{ticket.id} [P{ticket.priority}][{ticket.status}] - {ticket.title}")


@ticket_app.command("edit", help="Open a ticket in $EDITOR.")
def ticket_edit(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Open a ticket file in the default editor."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    _, ticket_path = result
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(ticket_path)])


def main() -> None:
    app()


if __name__ == "__main__":
    main()
