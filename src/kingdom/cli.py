"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
from datetime import UTC
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from kingdom.breakdown import build_breakdown_template, parse_breakdown_tickets
from kingdom.council import Council
from kingdom.design import build_design_template
from kingdom.session import get_current_thread, set_current_thread
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

    typer.echo(f"Warning: current branch '{current}' does not match feature '{feature}'.")


@app.command(help="Initialize .kd/ directory structure.")
def init(
    no_git: Annotated[bool, typer.Option("--no-git", help="Skip git repository check.")] = False,
    no_gitignore: Annotated[bool, typer.Option("--no-gitignore", help="Skip .gitignore creation.")] = False,
) -> None:
    """Initialize the .kd/ directory structure for Kingdom.

    Idempotent: creates missing pieces, skips existing.
    """
    base = Path.cwd()

    if not no_git and not is_git_repo(base):
        typer.echo("Error: Not a git repository. Use --no-git to initialize anyway.")
        raise typer.Exit(code=1)

    paths = ensure_base_layout(base, create_gitignore=not no_gitignore)
    from kingdom.agent import create_default_agent_files

    create_default_agent_files(base)
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
    branch: Annotated[str | None, typer.Argument(help="Branch name (defaults to current git branch).")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Force start even if a run is already active.")] = False,
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
    feature: Annotated[str | None, typer.Argument(help="Branch name (defaults to current run).")] = None,
) -> None:
    """Mark a run as complete, archive it, and clear the current run pointer."""
    import shutil
    from datetime import datetime

    base = Path.cwd()

    # Resolve feature: use argument or fall back to current run
    if feature is None:
        try:
            feature = resolve_current_run(base)
        except RuntimeError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

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
    state["done_at"] = datetime.now(UTC).isoformat()
    write_json(state_path, state)

    # Determine archive destination
    archive_base = state_root(base) / "archive"
    archive_base.mkdir(parents=True, exist_ok=True)
    archive_dest = archive_base / normalized

    # Handle collision: add timestamp suffix if destination exists
    if archive_dest.exists():
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        archive_dest = archive_base / f"{normalized}-{timestamp}"

    # Move branch folder to archive
    shutil.move(str(source_dir), str(archive_dest))

    # Clean up associated worktrees
    worktree_dir = state_root(base) / "worktrees" / normalized
    if worktree_dir.exists():
        # Remove git worktree first
        for worktree in worktree_dir.iterdir():
            if worktree.is_dir():
                result = subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    typer.echo(f"Warning: Failed to remove worktree {worktree.name}: {result.stderr.strip()}")
        # Remove the parent worktree directory if empty
        try:
            worktree_dir.rmdir()
        except OSError as e:
            typer.echo(f"Warning: Could not remove worktree directory: {e}")

    # Clear current run pointer (only if this was the current run)
    current_path = state_root(base) / "current"
    if current_path.exists():
        current_feature = current_path.read_text(encoding="utf-8").strip()
        if current_feature == normalized:
            clear_current_run(base)

    typer.echo(f"Archived '{feature}' to {archive_dest.relative_to(base)}")


council_app = typer.Typer(name="council", help="Query council members.")
app.add_typer(council_app, name="council")


@council_app.command("ask", help="Query council members.")
def council_ask(
    prompt: Annotated[str, typer.Argument(help="Prompt to send to council members.")],
    to: Annotated[str | None, typer.Option("--to", help="Send to a specific member only.")] = None,
    thread: Annotated[str | None, typer.Option("--thread", help="'new' to start a fresh thread.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON format.")] = False,
    timeout: Annotated[int, typer.Option("--timeout", help="Per-model timeout in seconds.")] = 120,
) -> None:
    """Query council members via threaded conversations."""
    from kingdom.thread import add_message, create_thread

    base = Path.cwd()
    feature = resolve_current_run(base)

    logs_dir = logs_root(base, feature)
    logs_dir.mkdir(parents=True, exist_ok=True)

    console = Console()

    c = Council.create(logs_dir=logs_dir, base=base)
    c.timeout = timeout
    c.load_sessions(base, feature)

    # Validate --to target
    if to:
        member = c.get_member(to)
        if member is None:
            available = [m.name for m in c.members]
            typer.echo(f"Unknown member: {to}")
            typer.echo(f"Available: {', '.join(available)}")
            raise typer.Exit(code=1)

    # Determine thread: continue current, or create new
    current = get_current_thread(base, feature)

    if thread == "new" or current is None:
        thread_id = f"council-{secrets.token_hex(2)}"
        member_names = [m.name for m in c.members]
        create_thread(base, feature, thread_id, ["king", *member_names], "council")
        set_current_thread(base, feature, thread_id)
    else:
        thread_id = current

    # Write king's message to thread
    target = to or "all"
    add_message(base, feature, thread_id, from_="king", to=target, body=prompt)

    # Query members
    if to:
        if not json_output:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(f"Querying {to}...", total=None)
                response = member.query(prompt, timeout)
                progress.update(task, description="Done")
        else:
            response = member.query(prompt, timeout)
        responses = {to: response}
    else:
        responses = query_with_progress(c, prompt, json_output, console)

    # Write each response as a message to the thread
    for name, response in responses.items():
        body = response.text if response.text else f"*Error: {response.error}*"
        add_message(base, feature, thread_id, from_=name, to="king", body=body)

    c.save_sessions(base, feature)

    # Display results
    if json_output:
        output = {
            "thread_id": thread_id,
            "responses": {
                name: {
                    "text": r.text,
                    "error": r.error,
                    "elapsed": r.elapsed,
                }
                for name, r in responses.items()
            },
        }
        print(json.dumps(output, indent=2))
    else:
        display_rich_panels(responses, thread_id, console)


@council_app.command("reset", help="Clear all council sessions.")
def council_reset() -> None:
    """Clear all council member sessions."""
    base = Path.cwd()
    feature = resolve_current_run(base)

    logs_dir = logs_root(base, feature)

    # Ensure directories exist
    logs_dir.mkdir(parents=True, exist_ok=True)

    c = Council.create(logs_dir=logs_dir, base=base)
    c.load_sessions(base, feature)
    c.reset_sessions()
    c.save_sessions(base, feature)
    typer.echo("Sessions cleared.")


@council_app.command("show", help="Display a council thread or legacy run.")
def council_show(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID or legacy run ID.")] = None,
) -> None:
    """Display a council thread's message history, or a legacy run."""
    from kingdom.thread import list_messages, thread_dir

    base = Path.cwd()
    feature = resolve_current_run(base)
    console = Console()

    # Resolve thread_id: argument, current thread, or error
    if thread_id is None:
        thread_id = get_current_thread(base, feature)
        if thread_id is None:
            typer.echo("No current council thread. Use `kd council ask` first.")
            raise typer.Exit(code=1)

    # Try as a thread first
    tdir = thread_dir(base, feature, thread_id)
    if tdir.exists():
        messages = list_messages(base, feature, thread_id)
        if not messages:
            typer.echo(f"Thread {thread_id}: no messages.")
            raise typer.Exit(code=1)

        console.print(f"[bold]Thread: {thread_id}[/bold]")
        console.print(f"[dim]{len(messages)} messages[/dim]\n")

        for msg in messages:
            ts = msg.timestamp.strftime("%H:%M:%S")
            subtitle = f"{ts} · to {msg.to}"
            border = "green" if msg.from_ == "king" else "blue"
            panel = Panel(
                Markdown(msg.body),
                title=msg.from_,
                subtitle=subtitle,
                border_style=border,
            )
            console.print(panel)
            console.print()
        return

    # Fall back to legacy run bundle in logs/council/
    council_logs_dir = council_logs_root(base, feature)
    run_dir = council_logs_dir / thread_id
    if not run_dir.exists():
        # Try 'last' alias
        if thread_id == "last":
            runs = [d for d in council_logs_dir.iterdir() if d.is_dir() and d.name.startswith("run-")]
            if not runs:
                typer.echo("No council runs found.")
                raise typer.Exit(code=1)
            run_dir = max(runs, key=lambda d: d.stat().st_mtime)
        else:
            typer.echo(f"Thread or run not found: {thread_id}")
            raise typer.Exit(code=1)

    # Display legacy run
    metadata_path = run_dir / "metadata.json"
    if metadata_path.exists():
        metadata = read_json(metadata_path)
        typer.echo(f"Run: {run_dir.name}")
        typer.echo(f"Timestamp: {metadata.get('timestamp', 'unknown')}")
        prompt_text = metadata.get("prompt", "unknown")
        typer.echo(f"Prompt: {prompt_text[:100]}...")
        typer.echo()

    for md_file in sorted(run_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        console.print(Panel(Markdown(content), title=md_file.stem, border_style="blue"))

    typer.echo(f"\n[dim]Legacy run: {run_dir}[/dim]")


@council_app.command("list", help="List all council threads.")
def council_list() -> None:
    """Show all council threads with message counts."""
    from kingdom.thread import list_threads, next_message_number, thread_dir

    base = Path.cwd()
    feature = resolve_current_run(base)
    current = get_current_thread(base, feature)

    threads = list_threads(base, feature)
    council_threads = [t for t in threads if t.pattern == "council"]

    if not council_threads:
        typer.echo("No council threads.")
        return

    for t in council_threads:
        tdir = thread_dir(base, feature, t.id)
        msg_count = next_message_number(tdir) - 1
        created = t.created_at.strftime("%Y-%m-%d %H:%M")
        marker = " *" if t.id == current else ""
        typer.echo(f"{t.id}  {created}  {msg_count} msgs{marker}")


def query_with_progress(council, prompt, json_output, console):
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


def display_rich_panels(responses, thread_id, console):
    """Display responses as Rich panels with Markdown."""
    for name in sorted(responses.keys()):
        response = responses[name]

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

    console.print(f"[dim]Thread: {thread_id}[/dim]")


design_app = typer.Typer(name="design", help="Manage design documents.")
app.add_typer(design_app, name="design")


def get_branch_paths(base: Path, feature: str) -> tuple[Path, Path, Path, Path]:
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


def get_design_paths(base: Path, feature: str) -> tuple[Path, Path]:
    """Get design.md and state.json paths, preferring branch structure."""
    _, design_path, _, state_path = get_branch_paths(base, feature)
    return design_path, state_path


@design_app.callback(invoke_without_command=True)
def design_default(ctx: typer.Context) -> None:
    """Draft the design doc (creates template if empty)."""
    if ctx.invoked_subcommand is not None:
        return
    base = Path.cwd()
    feature = resolve_current_run(base)
    design_path, _ = get_design_paths(base, feature)

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
    design_path, _ = get_design_paths(base, feature)

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
    design_path, state_path = get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        typer.echo("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    state = read_json(state_path) if state_path.exists() else {}
    state["design_approved"] = True
    write_json(state_path, state)
    typer.echo("Design approved.")


@app.command(help="Draft or iterate the current breakdown.")
def breakdown(
    apply: bool = typer.Option(False, "--apply", help="Create tickets from breakdown.md."),
) -> None:
    from datetime import datetime

    base = Path.cwd()
    feature = resolve_current_run(base)
    _, _, breakdown_path, state_path = get_branch_paths(base, feature)

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
    tickets_dir = get_tickets_dir(base)
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
            created=datetime.now(UTC),
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
    clean: Annotated[bool, typer.Option("--clean", help="Remove the worktree instead of creating.")] = False,
) -> None:
    """Create or remove a git worktree for ticket development."""
    base = Path.cwd()

    # Find the ticket
    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

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
            _, state_path = get_design_paths(base, feature)
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
        _, state_path = get_design_paths(base, feature)
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


def get_doc_status(path: Path) -> str:
    """Get status of a markdown doc: 'empty', 'draft', or path."""
    if not path.exists():
        return "missing"
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return "empty"
    return "present"


@app.command(help="Show current branch, design doc status, and breakdown status.")
def status(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON for machine consumption.")] = False,
) -> None:
    base = Path.cwd()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from None

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
    design_status = get_doc_status(design_path)
    breakdown_status = get_doc_status(breakdown_path)

    # Get design doc path relative to base for display
    design_path_str = str(design_path.relative_to(base)) if design_path.exists() else None

    # Get ticket counts
    tickets_dir = get_tickets_dir(base)
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
        all_deps_closed = all(status_by_id.get(dep, "unknown") == "closed" for dep in ticket.deps)
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
        typer.echo(
            f"Tickets: {status_counts['open']} open, {status_counts['in_progress']} in progress, {status_counts['closed']} closed ({total} total)"
        )
        typer.echo(f"Ready: {ready_count}")


def check_cli(command: list[str]) -> tuple[bool, str | None]:
    """Check if a CLI command is available."""
    try:
        subprocess.run(command, capture_output=True, timeout=5)
        return (True, None)
    except FileNotFoundError:
        return (False, "Command not found")
    except subprocess.TimeoutExpired:
        return (False, "Command timed out")


def get_doctor_checks(base: Path) -> list[dict[str, str | list[str]]]:
    """Build doctor checks from agent configs."""
    import shlex

    from kingdom.agent import DEFAULT_AGENTS, list_agents

    agents = list_agents(base) or list(DEFAULT_AGENTS.values())

    checks: list[dict[str, str | list[str]]] = []
    for agent in agents:
        version_cmd = agent.version_command or f"{shlex.split(agent.cli)[0]} --version"
        checks.append(
            {
                "name": agent.name,
                "command": shlex.split(version_cmd),
                "install_hint": agent.install_hint or f"Install {agent.name}",
            }
        )
    return checks


@app.command(help="Check if agent CLIs are installed.")
def doctor(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Verify agent CLIs are installed and provide guidance."""
    base = Path.cwd()
    doctor_checks = get_doctor_checks(base)
    results: dict[str, dict[str, bool | str | None]] = {}
    issues: list[dict[str, str]] = []

    for check in doctor_checks:
        installed, error = check_cli(check["command"])
        results[check["name"]] = {"installed": installed, "error": error}
        if not installed:
            issues.append({"name": check["name"], "hint": check["install_hint"]})

    if output_json:
        print(json.dumps(results, indent=2))
    else:
        console = Console()
        console.print("\nAgent CLIs:")
        for check in doctor_checks:
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


def get_tickets_dir(base: Path, backlog: bool = False) -> Path:
    """Get the tickets directory for the current context."""
    if backlog:
        return backlog_root(base) / "tickets"

    # Try to get current branch's tickets directory
    try:
        feature = resolve_current_run(base)
        normalize_branch_name(feature)
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
    description: Annotated[str | None, typer.Option("-d", "--description", help="Ticket description.")] = None,
    priority: Annotated[int, typer.Option("-p", "--priority", help="Priority (1-3, 1 is highest).")] = 2,
    ticket_type: Annotated[str, typer.Option("-t", "--type", help="Ticket type (task, bug, feature).")] = "task",
    backlog: Annotated[bool, typer.Option("--backlog", help="Create in backlog instead of current branch.")] = False,
) -> None:
    """Create a new ticket in the current branch or backlog."""
    from datetime import datetime

    base = Path.cwd()

    # Validate priority range (1-3)
    if priority < 1 or priority > 3:
        typer.echo(f"Warning: Priority {priority} outside valid range (1-3), clamping.")
        priority = max(1, min(3, priority))

    # Ensure base layout exists
    ensure_base_layout(base)

    tickets_dir = get_tickets_dir(base, backlog=backlog)
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
        created=datetime.now(UTC),
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
    all_tickets: Annotated[bool, typer.Option("--all", "-a", help="List all tickets across all locations.")] = False,
    backlog: Annotated[bool, typer.Option("--backlog", help="List open tickets in backlog only.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """List tickets in the current branch or all locations."""
    base = Path.cwd()

    if backlog:
        backlog_tickets = backlog_root(base) / "tickets"
        tickets = list_tickets(backlog_tickets) if backlog_tickets.exists() else []
        tickets = [t for t in tickets if t.status != "closed"]

        if output_json:
            results = [
                {
                    "id": t.id,
                    "priority": t.priority,
                    "status": t.status,
                    "title": t.title,
                    "location": "backlog",
                }
                for t in tickets
            ]
            typer.echo(json.dumps(results, indent=2))
        else:
            if not tickets:
                typer.echo("No backlog tickets.")
                return
            for ticket in tickets:
                typer.echo(f"{ticket.id} [P{ticket.priority}][{ticket.status}] - {ticket.title}")
        return

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
                all_results.append(
                    {
                        "id": ticket.id,
                        "priority": ticket.priority,
                        "status": ticket.status,
                        "title": ticket.title,
                        "location": location_name,
                    }
                )

        if output_json:
            typer.echo(json.dumps(all_results, indent=2))
        else:
            for item in all_results:
                loc = item["location"]
                typer.echo(f"{item['id']} [P{item['priority']}][{item['status']}] - {item['title']} ({loc})")
    else:
        # List tickets for current branch only
        tickets_dir = get_tickets_dir(base)
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
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Display a ticket by ID (supports partial matching)."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

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


def update_ticket_status(ticket_id: str, new_status: str) -> None:
    """Helper to update a ticket's status."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

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
    update_ticket_status(ticket_id, "in_progress")


@ticket_app.command("close", help="Mark a ticket as closed.")
def ticket_close(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status to closed."""
    update_ticket_status(ticket_id, "closed")


@ticket_app.command("reopen", help="Reopen a closed ticket.")
def ticket_reopen(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status back to open."""
    update_ticket_status(ticket_id, "open")


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
        raise typer.Exit(code=1) from None

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
        raise typer.Exit(code=1) from None

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
        raise typer.Exit(code=1) from None

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
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
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
        raise typer.Exit(code=1) from None

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
