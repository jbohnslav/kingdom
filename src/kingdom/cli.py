"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import signal
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NamedTuple

if TYPE_CHECKING:
    from kingdom.thread import ThreadStatus

import typer
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from kingdom.breakdown import build_breakdown_template
from kingdom.council import Council
from kingdom.design import build_design_template, ensure_design_initialized
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
    STATUSES,
    AmbiguousTicketMatch,
    Ticket,
    find_newly_unblocked,
    find_ticket,
    generate_ticket_id,
    list_tickets,
    move_ticket,
    read_ticket,
    write_ticket,
)

error_console = Console(stderr=True)


def print_error(message: str) -> None:
    """Print a consistently styled error message to stderr."""
    error_console.print(f"[bold red]Error:[/bold red] {message}")


def is_branch_done(branch_dir: Path) -> bool:
    """Check if a branch directory has status 'done' in its state.json."""
    state_path = branch_dir / "state.json"
    if state_path.exists():
        state = read_json(state_path)
        return state.get("status") == "done"
    return False


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
        typer.echo(f"Created branch {feature}")
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
        print_error("Not a git repository. Use --no-git to initialize anyway.")
        raise typer.Exit(code=1)

    paths = ensure_base_layout(base, create_gitignore=not no_gitignore)

    # Scaffold config.json with defaults (idempotent)
    from kingdom.config import default_config

    config_path = paths["state_root"] / "config.json"
    if not config_path.exists():
        import json

        cfg = default_config()
        data = {
            "agents": {name: {"backend": a.backend} for name, a in cfg.agents.items()},
            "council": {"members": cfg.council.members, "timeout": cfg.council.timeout},
            "peasant": {
                "agent": cfg.peasant.agent,
                "timeout": cfg.peasant.timeout,
                "max_iterations": cfg.peasant.max_iterations,
            },
        }
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    typer.echo(f"Initialized {paths['state_root']}")


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


@app.command(help="Initialize a branch-based session and state.")
def start(
    branch: Annotated[str | None, typer.Argument(help="Branch name (defaults to current git branch).")] = None,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force start even if a session is already active.")
    ] = False,
) -> None:
    base = Path.cwd()

    # Auto-init if .kd/ doesn't exist (with git check)
    if not state_root(base).exists():
        if not is_git_repo(base):
            print_error("Not a git repository. Run `kd init --no-git` first.")
            raise typer.Exit(code=1)
        typer.echo("Auto-initializing .kd/ directory...")
        ensure_base_layout(base)

    # Check for existing current run
    current_path = state_root(base) / "current"
    if current_path.exists() and not force:
        existing = current_path.read_text(encoding="utf-8").strip()
        print_error(f"A session is already active: {existing}")
        error_console.print("  Use --force to override, or run `kd done` first.")
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


@app.command(help="Mark the current session as done.")
def done(
    feature: Annotated[str | None, typer.Argument(help="Branch name (defaults to current session).")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Close even if open tickets remain.")] = False,
) -> None:
    """Mark a session as done (status transition only, no file moves)."""
    from datetime import datetime

    base = Path.cwd()

    # Resolve feature: use argument or fall back to current session
    if feature is None:
        try:
            feature = resolve_current_run(base)
        except RuntimeError:
            typer.echo("No active session. Pass the branch name: `kd done <branch>`")
            raise typer.Exit(code=1) from None

    # Get the branch directory (normalized name)
    normalized = normalize_branch_name(feature)
    source_dir = branch_root(base, feature)

    # Check if it exists
    if not source_dir.exists():
        # Fall back to legacy runs structure
        legacy_dir = state_root(base) / "runs" / feature
        if legacy_dir.exists():
            source_dir = legacy_dir
        else:
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

    # Clean up associated worktrees
    worktree_dir = state_root(base) / "worktrees" / normalized
    if worktree_dir.exists():
        for worktree in worktree_dir.iterdir():
            if worktree.is_dir():
                result = subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    typer.echo(f"Warning: Failed to remove worktree {worktree.name}: {result.stderr.strip()}")
        try:
            worktree_dir.rmdir()
        except OSError as e:
            typer.echo(f"Warning: Could not remove worktree directory: {e}")

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

    # Check for unpushed commits
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
    except (subprocess.SubprocessError, ValueError):
        pass

    if push_reminder:
        lines.append(push_reminder)

    body = "\n".join(lines) if lines else "[dim]No additional info[/dim]"
    panel = Panel(body, title=f"[bold green]Done: {feature}[/bold green]", border_style="green")
    console.print(panel)


council_app = typer.Typer(name="council", help="Query council members.")
app.add_typer(council_app, name="council")


def resolve_council_thread_id(
    base: Path,
    feature: str,
    thread_id: str | None,
    *,
    command: str = "show",
) -> str:
    """Resolve a council thread ID from user input, current pointer, or most-recent fallback.

    Resolution order:
      1. If *thread_id* is given, resolve by exact or prefix match.
      2. If not given, use the current_thread pointer.
      3. If no current pointer, fall back to the most recently created council thread.

    Prints informative messages when falling back and detailed errors
    (with suggestions) when resolution fails.

    Returns:
        Resolved thread ID string.

    Raises:
        typer.Exit(code=1): On any resolution failure.
    """
    from kingdom.thread import (
        AmbiguousThreadMatch,
        ThreadNotFoundError,
        list_threads,
        resolve_thread,
    )

    # Case 1: explicit thread_id provided -- resolve with prefix matching
    if thread_id is not None:
        try:
            meta = resolve_thread(base, feature, thread_id, pattern="council")
            return meta.id
        except AmbiguousThreadMatch as exc:
            typer.echo(f"'{thread_id}' matches multiple threads:")
            for m in exc.matches:
                topic = topic_for_thread(base, feature, m.id)
                label = f"  {m.id}  {m.created_at.strftime('%Y-%m-%d %H:%M')}"
                if topic:
                    label += f"  {topic}"
                typer.echo(label)
            typer.echo(f"\nBe more specific, e.g.: kd council {command} {exc.matches[0].id}")
            raise typer.Exit(code=1) from None
        except ThreadNotFoundError as exc:
            typer.echo(f"Thread not found: {thread_id}")
            if exc.available:
                typer.echo("\nAvailable council threads:")
                for t in exc.available[-5:]:
                    topic = topic_for_thread(base, feature, t.id)
                    label = f"  {t.id}  {t.created_at.strftime('%Y-%m-%d %H:%M')}"
                    if topic:
                        label += f"  {topic}"
                    typer.echo(label)
                if len(exc.available) > 5:
                    typer.echo(f"  ... and {len(exc.available) - 5} more (use `kd council list`)")
            else:
                typer.echo("No council threads exist. Use `kd council ask` to start one.")
            raise typer.Exit(code=1) from None

    # Case 2: no explicit thread_id -- try current_thread pointer
    current = get_current_thread(base, feature)
    if current is not None:
        from kingdom.thread import thread_dir

        tdir = thread_dir(base, feature, current)
        if tdir.exists():
            return current
        # Stale pointer -- fall through to most-recent

    # Case 3: fall back to most recently created council thread
    threads = list_threads(base, feature)
    council_threads = [t for t in threads if t.pattern == "council"]
    if council_threads:
        picked = council_threads[-1]  # sorted by created_at asc
        typer.echo(f"Using most recent thread: {picked.id}")
        return picked.id

    # No threads at all
    typer.echo("No council threads. Use `kd council ask` to start one.")
    raise typer.Exit(code=1)


def topic_for_thread(base: Path, feature: str, thread_id: str) -> str:
    """Return the first king message body (truncated) as a topic summary, or empty string."""
    from kingdom.thread import list_messages

    try:
        messages = list_messages(base, feature, thread_id)
    except FileNotFoundError:
        return ""
    for msg in messages:
        if msg.from_ == "king":
            first_line = msg.body.strip().split("\n", 1)[0]
            if len(first_line) > 60:
                return first_line[:60] + "..."
            return first_line
    return ""


@council_app.command("ask", help="Query council members.")
def council_ask(
    prompt: Annotated[str, typer.Argument(help="Prompt to send to council members.")],
    to: Annotated[str | None, typer.Option("--to", help="Send to a specific member only.")] = None,
    new_thread: Annotated[bool, typer.Option("--new-thread", help="Start a fresh thread.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON format.")] = False,
    async_mode: Annotated[
        bool, typer.Option("--async", help="Dispatch in background, then watch for responses.")
    ] = False,
    no_watch: Annotated[bool, typer.Option("--no-watch", help="With --async, dispatch only without watching.")] = False,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Per-model timeout in seconds.")] = None,
    writable: Annotated[
        bool, typer.Option("--writable", "-w", help="Grant council members full write permissions.")
    ] = False,
) -> None:
    """Query council members via threaded conversations.

    Default: blocks in-process until all responses arrive, rendering as they come.
    Use --async to dispatch agents in background and watch for responses.
    Use --async --no-watch to dispatch and return immediately.
    Use --json for machine-readable batch output.
    """
    import re

    from kingdom.thread import add_message, create_thread, thread_dir

    base = Path.cwd()
    feature = resolve_current_run(base)

    logs_dir = logs_root(base, feature)
    logs_dir.mkdir(parents=True, exist_ok=True)

    console = Console()

    c = Council.create(logs_dir=logs_dir, base=base)
    if writable:
        for m in c.members:
            m.writable = True
    if timeout is not None:
        c.timeout = timeout
    timeout = c.timeout
    c.load_sessions(base, feature)

    # Parse @mentions from prompt (kin-09c9)
    available_names = {m.name for m in c.members}
    if not to:
        mentions = re.findall(r"(?<!\w)@(\w+)", prompt)
        if mentions:
            if "all" in mentions:
                # @all = query everyone, strip @all from prompt
                prompt = re.sub(r"(?<!\w)@all\b\s*", "", prompt).strip()
            else:
                unknown = [m for m in mentions if m not in available_names]
                if unknown:
                    typer.echo(f"Unknown @mention(s): {', '.join(unknown)}")
                    typer.echo(f"Available: {', '.join(sorted(available_names))}")
                    raise typer.Exit(code=1)
                # Use mentioned members as targets
                to = mentions[0] if len(mentions) == 1 else None
                target_members = [m for m in mentions if m in available_names]
                if len(target_members) > 1:
                    # Multiple @mentions: filter council to just those members
                    c.members = [m for m in c.members if m.name in set(target_members)]

    # Validate --to target
    member = None
    if to:
        member = c.get_member(to)
        if member is None:
            typer.echo(f"Unknown member: {to}")
            typer.echo(f"Available: {', '.join(sorted(available_names))}")
            raise typer.Exit(code=1)

    # Determine thread: continue current, or create new
    current = get_current_thread(base, feature)
    start_new = new_thread or current is None

    # Recover from stale pointer: current_thread set but directory missing
    if not start_new and not thread_dir(base, feature, current).exists():
        set_current_thread(base, feature, None)
        start_new = True

    if start_new:
        thread_id = f"council-{secrets.token_hex(2)}"
        if to:
            member_names = [to]
        else:
            member_names = [m.name for m in c.members]
        create_thread(base, feature, thread_id, ["king", *member_names], "council")
        set_current_thread(base, feature, thread_id)
    else:
        thread_id = current

    # Write king's message to thread
    target = to or "all"
    add_message(base, feature, thread_id, from_="king", to=target, body=prompt)

    # --json mode: batch query (always sync, no streaming)
    if json_output:
        if to and member:
            response = member.query(prompt, timeout)
            responses = {to: response}
            add_message(base, feature, thread_id, from_=to, to="king", body=response.thread_body())
        else:
            responses = query_with_progress(c, prompt, json_output, console)
            for name, resp in responses.items():
                add_message(base, feature, thread_id, from_=name, to="king", body=resp.thread_body())

        c.save_sessions(base, feature)

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
        console.print_json(json.dumps(output, indent=2))
        return

    # --async mode: dispatch agents in background, then watch
    if async_mode:
        member_names_str = to if to else ", ".join(m.name for m in c.members)
        console.print(f"[dim]Thread: {thread_id}[/dim]")
        console.print(f"[dim]Querying: {member_names_str}...[/dim]\n")

        worker_cmd = [
            sys.executable,
            "-m",
            "kingdom.council.worker",
            "--base",
            str(base),
            "--feature",
            feature,
            "--thread-id",
            thread_id,
            "--prompt",
            prompt,
            "--timeout",
            str(timeout if timeout is not None else c.timeout),
        ]
        if to:
            worker_cmd.extend(["--to", to])
        if writable:
            worker_cmd.append("--writable")

        subprocess.Popen(
            worker_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

        if no_watch:
            typer.echo(f"Dispatched — use `kd council watch {thread_id}` to see responses")
            return

        # Fall through to watch — poll thread dir and render panels as they arrive
        ask_expected = {to} if to else {m.name for m in c.members}
        watch_thread(thread_id=thread_id, timeout=timeout + 30, expected=ask_expected)
        return

    # Default: block in-process until all responses arrive
    member_names_str = to if to else ", ".join(m.name for m in c.members)
    console.print(f"[dim]Thread: {thread_id}[/dim]")
    console.print(f"[dim]Querying: {member_names_str}...[/dim]\n")

    if to and member:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Querying {to}...", total=None)
            response = member.query(prompt, timeout)
            progress.update(task, description="Done")
        add_message(base, feature, thread_id, from_=to, to="king", body=response.thread_body())
        render_response(response, console)
    else:

        def on_response(name, response):
            render_response(response, console)

        c.query_to_thread(prompt, base, feature, thread_id, callback=on_response)

    c.save_sessions(base, feature)


@council_app.command("reset", help="Clear council sessions.")
def council_reset(
    member_name: Annotated[str | None, typer.Option("--member", help="Reset only this member's session.")] = None,
) -> None:
    """Clear council member sessions. Use --member to reset a single member."""
    base = Path.cwd()
    feature = resolve_current_run(base)

    logs_dir = logs_root(base, feature)

    # Ensure directories exist
    logs_dir.mkdir(parents=True, exist_ok=True)

    c = Council.create(logs_dir=logs_dir, base=base)
    c.load_sessions(base, feature)

    if member_name:
        m = c.get_member(member_name)
        if m is None:
            available = ", ".join(sorted(mem.name for mem in c.members))
            typer.echo(f"Unknown member: {member_name}")
            typer.echo(f"Available: {available}")
            raise typer.Exit(code=1)
        m.reset_session()
        c.save_sessions(base, feature)
        typer.echo(f"Session cleared for {member_name}")
    else:
        c.reset_sessions()
        c.save_sessions(base, feature)
        typer.echo("All sessions cleared")


def group_messages_into_turns(messages: list) -> list[list]:
    """Group messages into conversational turns.

    A turn = one king message + all member responses before the next king message.
    Messages before the first king message (if any) form turn 0.
    """
    if not messages:
        return []

    turns: list[list] = []
    current_turn: list = []

    for msg in messages:
        if msg.from_ == "king" and current_turn:
            turns.append(current_turn)
            current_turn = []
        current_turn.append(msg)

    if current_turn:
        turns.append(current_turn)

    return turns


def print_turn(console: Console, turn_msgs: list, turn_number: int, total_turns: int) -> None:
    """Print a single conversational turn with header and separator."""
    first_msg = turn_msgs[0]
    ts = first_msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"[bold cyan]── Turn {turn_number}/{total_turns} ── {ts} ──[/bold cyan]")
    console.print()

    for msg in turn_msgs:
        msg_ts = msg.timestamp.strftime("%H:%M:%S")
        subtitle = f"{msg_ts} · to {msg.to}"
        header = f"## [{subtitle}] {msg.from_}"
        console.print(Markdown(f"{header}\n\n{msg.body}"))
        console.print()


def show_legacy_run(base: Path, feature: str, thread_id: str, console: Console) -> None:
    """Display a legacy run-bundle from logs/council/."""
    council_logs_dir = council_logs_root(base, feature)
    run_dir = council_logs_dir / thread_id
    if not run_dir.exists():
        # Try 'last' alias
        if thread_id == "last":
            if not council_logs_dir.exists():
                typer.echo('No council history found. Start a conversation with `kd council ask "prompt"`.')
                raise typer.Exit(code=1)
            runs = [d for d in council_logs_dir.iterdir() if d.is_dir() and d.name.startswith("run-")]
            if not runs:
                typer.echo('No council history found. Start a conversation with `kd council ask "prompt"`.')
                raise typer.Exit(code=1)
            run_dir = max(runs, key=lambda d: d.stat().st_mtime)
        else:
            typer.echo(f"Legacy run not found: {thread_id}")
            raise typer.Exit(code=1)

    metadata_path = run_dir / "metadata.json"
    if metadata_path.exists():
        metadata = read_json(metadata_path)
        typer.echo(f"Session: {run_dir.name}")
        typer.echo(f"Timestamp: {metadata.get('timestamp', 'unknown')}")
        prompt_text = metadata.get("prompt", "unknown")
        typer.echo(f"Prompt: {prompt_text[:100]}...")
        typer.echo()

    for md_file in sorted(run_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        console.print(Markdown(f"## {md_file.stem}\n\n{content}"))

    console.print(f"\n[dim]Archived session: {run_dir}[/dim]")


@council_app.command("show", help="Display a council thread.")
def council_show(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID.")] = None,
    last_n: Annotated[int | None, typer.Option("--last", help="Show last N turns.")] = None,
    show_all: Annotated[bool, typer.Option("--all", help="Show full thread history.")] = False,
) -> None:
    """Display a council thread's message history."""
    from kingdom.thread import list_messages

    base = Path.cwd()
    feature = resolve_current_run(base)
    console = Console()

    # Legacy run-bundle support: "last" alias and "run-*" IDs bypass thread resolution
    if thread_id is not None and (thread_id == "last" or thread_id.startswith("run-")):
        show_legacy_run(base, feature, thread_id, console)
        return

    # Resolve via prefix matching / current pointer / most-recent fallback
    thread_id = resolve_council_thread_id(base, feature, thread_id, command="show")

    messages = list_messages(base, feature, thread_id)
    if not messages:
        typer.echo(f'Thread {thread_id}: no messages. Send one with `kd council ask "prompt"`.')
        raise typer.Exit(code=1)

    turns = group_messages_into_turns(messages)
    total_turns = len(turns)
    total_msgs = len(messages)

    # Determine which turns to show
    if show_all:
        visible_turns = turns
        start_index = 0
    elif last_n is not None:
        n = min(last_n, total_turns)
        visible_turns = turns[-n:]
        start_index = total_turns - n
    else:
        # Default: show only the latest turn
        visible_turns = turns[-1:]
        start_index = total_turns - 1

    visible_msgs = sum(len(t) for t in visible_turns)
    hidden_turns = total_turns - len(visible_turns)

    def pl(n: int, word: str) -> str:
        return f"{n} {word}" if n == 1 else f"{n} {word}s"

    console.print(f"[bold]Thread: {thread_id}[/bold]")
    if hidden_turns > 0:
        console.print(
            f"[dim]Showing {pl(len(visible_turns), 'turn')} of {total_turns} "
            f"({pl(visible_msgs, 'message')} of {total_msgs}). "
            f"Use --all for full history.[/dim]"
        )
    else:
        console.print(f"[dim]{pl(total_turns, 'turn')}, {pl(total_msgs, 'message')}[/dim]")
    console.print()

    for i, turn_msgs in enumerate(visible_turns):
        turn_number = start_index + i + 1
        print_turn(console, turn_msgs, turn_number, total_turns)


@council_app.command("list", help="List all council threads.")
def council_list() -> None:
    """Show all council threads with topic summary and member status."""
    from kingdom.thread import (
        MEMBER_ERRORED,
        MEMBER_PENDING,
        MEMBER_RESPONDED,
        MEMBER_RUNNING,
        MEMBER_TIMED_OUT,
        list_messages,
        list_threads,
        thread_response_status,
    )

    base = Path.cwd()
    feature = resolve_current_run(base)
    current = get_current_thread(base, feature)
    console = Console()

    threads = list_threads(base, feature)
    council_threads = [t for t in threads if t.pattern == "council"]

    if not council_threads:
        typer.echo('No council threads. Start one with `kd council ask "prompt"`.')
        return

    state_symbols = {
        MEMBER_RESPONDED: ("[green]\u2713[/green]", "responded"),
        MEMBER_RUNNING: ("[yellow]\u25cb[/yellow]", "running"),
        MEMBER_ERRORED: ("[red]\u2717[/red]", "errored"),
        MEMBER_TIMED_OUT: ("[red]\u29d6[/red]", "timed out"),
        MEMBER_PENDING: ("[dim]\u2026[/dim]", "pending"),
    }

    for t in council_threads:
        marker = "[bold] *[/bold]" if t.id == current else ""
        created = t.created_at.strftime("%Y-%m-%d %H:%M")

        # Get topic from first king message
        messages = list_messages(base, feature, t.id)
        topic = ""
        for msg in messages:
            if msg.from_ == "king":
                first_line = msg.body.strip().split("\n", 1)[0]
                topic = first_line[:60] + ("\u2026" if len(first_line) > 60 else "")
                break

        # Get per-member status
        status = thread_response_status(base, feature, t.id)
        member_parts = []
        for name in sorted(status.member_states):
            ms = status.member_states[name]
            symbol, _label = state_symbols.get(ms.state, ("?", "unknown"))
            member_parts.append(f"{symbol} {name}")
        members_str = "  ".join(member_parts) if member_parts else ""

        console.print(f"[bold]{t.id}[/bold]  [dim]{created}[/dim]{marker}")
        if topic:
            console.print(f"  {topic}")
        if members_str:
            console.print(f"  {members_str}")
        console.print()

    # Print legend explaining the status symbols
    legend_parts = [f"{sym} {label}" for sym, label in state_symbols.values()]
    console.print(f"[dim]{' '.join(legend_parts)}[/dim]")


@council_app.command("ls", hidden=True)
def council_ls() -> None:
    """Alias for 'council list'."""
    council_list()


@council_app.command("status", help="Show response status for council threads.")
def council_status(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID (defaults to current/most recent).")] = None,
    all_threads: Annotated[bool, typer.Option("--all", help="Show status for all threads.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show log file paths.")] = False,
) -> None:
    """Show which councillors have responded and which are still pending."""
    from kingdom.thread import list_threads, thread_response_status

    base = Path.cwd()
    feature = resolve_current_run(base)

    if all_threads:
        threads = list_threads(base, feature)
        council_threads = [t for t in threads if t.pattern == "council"]
        if not council_threads:
            typer.echo('No council threads. Start one with `kd council ask "prompt"`.')
            return
        for t in council_threads:
            status = thread_response_status(base, feature, t.id)
            print_thread_status(status, base, feature, verbose)
            typer.echo()
        return

    # Single thread mode
    thread_id = resolve_council_thread_id(base, feature, thread_id, command="status")

    status = thread_response_status(base, feature, thread_id)
    print_thread_status(status, base, feature, verbose)


def print_thread_status(status: ThreadStatus, base: Path, feature: str, verbose: bool = False) -> None:
    """Print response status for a single thread with rich per-member states."""
    from kingdom.thread import (
        MEMBER_ERRORED,
        MEMBER_PENDING,
        MEMBER_RESPONDED,
        MEMBER_RUNNING,
        MEMBER_TIMED_OUT,
        thread_dir,
    )

    # Overall thread state
    has_errors = any(ms.state in (MEMBER_ERRORED, MEMBER_TIMED_OUT) for ms in status.member_states.values())
    has_running = any(ms.state == MEMBER_RUNNING for ms in status.member_states.values())

    if not status.pending and not has_errors:
        state_label = "[green]complete[/green]"
    elif has_running:
        state_label = "[blue]running[/blue]"
    elif has_errors and not status.pending:
        state_label = "[red]errors[/red]"
    else:
        state_label = "[yellow]waiting[/yellow]"

    console = Console(soft_wrap=True)
    console.print(f"{status.thread_id}  [{state_label}]")

    if verbose:
        tdir = thread_dir(base, feature, status.thread_id)
        console.print(f"  [dim]thread: {tdir.relative_to(base)}[/dim]")

    STATE_STYLES = {
        MEMBER_RESPONDED: "[green]responded[/green]",
        MEMBER_RUNNING: "[blue]running[/blue]",
        MEMBER_ERRORED: "[red]errored[/red]",
        MEMBER_TIMED_OUT: "[red]timed out[/red]",
        MEMBER_PENDING: "[yellow]pending[/yellow]",
    }

    for name in sorted(status.expected):
        ms = status.member_states.get(name)
        if ms:
            styled = STATE_STYLES.get(ms.state, ms.state)
            line = f"  {name}: {styled}"
            if verbose and ms.error:
                # Show truncated error detail
                err_preview = ms.error.replace("\n", " ")[:80]
                line += f"  [dim]{err_preview}[/dim]"
        else:
            # Fallback for missing member_states (backward compat)
            line = f"  {name}: {'responded' if name in status.responded else 'pending'}"

        if verbose:
            log_file = logs_root(base, feature) / f"council-{name}.log"
            if log_file.exists():
                line += f"  [dim]log={log_file.relative_to(base)}[/dim]"

        console.print(line)


def watch_thread(
    thread_id: str | None = None,
    timeout: int = 300,
    expected: set[str] | None = None,
) -> None:
    """Core watch logic — poll a thread, tail stream files, and render responses.

    While waiting for members to respond, tails .stream-{member}.jsonl files
    and displays incremental text as it arrives. When the finalized message file
    lands, renders the full response panel.

    Args:
        thread_id: Thread to watch (defaults to current).
        timeout: Max seconds to wait.
        expected: If set, only wait for these members instead of all thread members.
    """
    import time

    from rich.live import Live
    from rich.text import Text

    from kingdom.agent import extract_stream_text, resolve_all_agents
    from kingdom.config import load_config
    from kingdom.council.base import AgentResponse
    from kingdom.thread import get_thread, list_messages, thread_dir

    base = Path.cwd()
    feature = resolve_current_run(base)
    console = Console()

    # Resolve thread_id
    thread_id = resolve_council_thread_id(base, feature, thread_id, command="watch")

    tdir = thread_dir(base, feature, thread_id)

    # Use caller-provided expected set, or fall back to thread metadata
    if expected is not None:
        expected_members = expected
    else:
        meta = get_thread(base, feature, thread_id)
        expected_members = {m for m in meta.members if m != "king"}

    # Load agent configs for stream text extraction (best-effort — bad config
    # shouldn't prevent watching for finalized messages)
    member_backends: dict[str, str] = {}
    try:
        cfg = load_config(base)
        agent_configs = resolve_all_agents(cfg.agents)
        for name in expected_members:
            ac = agent_configs.get(name)
            if ac:
                member_backends[name] = ac.backend
    except Exception:
        pass  # Streaming preview won't work, but final messages still display

    console.print(f"[bold]Watching: {thread_id}[/bold]")
    console.print(f"[dim]Expecting: {', '.join(sorted(expected_members))}[/dim]\n")

    # Track which messages we've already rendered
    seen_sequences: set[int] = set()
    responded_members: set[str] = set()

    # Find the most recent king ask so we only consider responses to it
    messages = list_messages(base, feature, thread_id)
    last_ask_seq = 0
    for msg in messages:
        if msg.from_ == "king":
            last_ask_seq = msg.sequence

    # Render existing agent responses that came after the latest ask
    for msg in messages:
        seen_sequences.add(msg.sequence)
        if msg.sequence <= last_ask_seq:
            continue
        if msg.from_ != "king" and msg.from_ in expected_members:
            responded_members.add(msg.from_)
            response = AgentResponse(name=msg.from_, text=msg.body, elapsed=0.0)
            render_response(response, console)

    if responded_members >= expected_members:
        console.print("[dim]All members have responded.[/dim]")
        return

    # Stream tracking state
    stream_positions: dict[str, int] = {}  # member -> file byte offset
    accumulated_text: dict[str, str] = {}  # member -> accumulated streamed text
    streaming_members: set[str] = set()  # members with active stream files

    def build_status_display() -> Text:
        """Build a multi-line status display for the live area."""
        elapsed = int(time.monotonic() - start_time)
        lines: list[str] = []
        waiting = expected_members - responded_members

        for name in sorted(waiting):
            if name in streaming_members and name in accumulated_text:
                chars = len(accumulated_text[name])
                # Show last ~60 chars as preview
                preview = accumulated_text[name][-60:].replace("\n", " ")
                if len(accumulated_text[name]) > 60:
                    preview = "..." + preview
                lines.append(f"  {name}: streaming ({chars} chars) {preview}")
            else:
                lines.append(f"  {name}: waiting...")

        header = f"[{elapsed}s] Waiting for {len(waiting)} member(s):"
        return Text("\n".join([header, *lines]))

    def read_stream_files() -> None:
        """Read new lines from .stream-{member}.jsonl files."""
        for name in expected_members - responded_members:
            stream_file = tdir / f".stream-{name}.jsonl"
            if not stream_file.exists():
                if name in streaming_members:
                    # Stream file was deleted (member finished or retry) — reset tracking
                    streaming_members.discard(name)
                    stream_positions.pop(name, None)
                continue

            streaming_members.add(name)
            backend = member_backends.get(name, "")
            pos = stream_positions.get(name, 0)

            # Detect file recreation: during retry, the old stream file is deleted
            # and a new one created. If the new file is smaller than our saved offset,
            # reset to read from the beginning.
            try:
                file_size = stream_file.stat().st_size
                if file_size < pos:
                    pos = 0
                    accumulated_text.pop(name, None)
            except OSError:
                continue

            try:
                with open(stream_file, encoding="utf-8") as f:
                    f.seek(pos)
                    new_data = f.read()
                    new_pos = f.tell()
            except OSError:
                continue

            if not new_data or new_pos == pos:
                continue

            stream_positions[name] = new_pos
            # Process complete lines only
            for line in new_data.splitlines():
                if not line.strip():
                    continue
                text = extract_stream_text(line, backend)
                if text:
                    accumulated_text.setdefault(name, "")
                    accumulated_text[name] += text

    # Poll for new messages with live streaming display
    start_time = time.monotonic()
    try:
        with Live(build_status_display(), console=console, refresh_per_second=4) as live:
            while time.monotonic() - start_time < timeout:
                time.sleep(0.25)

                # Read stream files for live text
                read_stream_files()

                # Check for finalized messages
                messages = list_messages(base, feature, thread_id)
                for msg in messages:
                    if msg.sequence in seen_sequences:
                        continue
                    seen_sequences.add(msg.sequence)

                    if msg.from_ != "king" and msg.from_ in expected_members:
                        responded_members.add(msg.from_)
                        streaming_members.discard(msg.from_)
                        accumulated_text.pop(msg.from_, None)
                        stream_positions.pop(msg.from_, None)
                        # Print final response above the live area
                        response = AgentResponse(name=msg.from_, text=msg.body, elapsed=0.0)
                        live.console.print()
                        render_response(response, live.console)

                if responded_members >= expected_members:
                    live.update(Text(""))
                    live.console.print("[dim]All members have responded.[/dim]")
                    return

                live.update(build_status_display())
    except KeyboardInterrupt:
        console.print("\n[dim]Watch interrupted.[/dim]")
        return

    console.print(f"[yellow]Timeout after {timeout}s. Received from: {', '.join(sorted(responded_members))}[/yellow]")
    missing = expected_members - responded_members
    if missing:
        console.print(f"[yellow]Missing: {', '.join(sorted(missing))}[/yellow]")


@council_app.command("watch", help="Watch a council thread for incoming responses.")
def council_watch(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID (defaults to current).")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Max seconds to wait.")] = 300,
) -> None:
    """Watch a council thread and render agent responses as they arrive."""
    watch_thread(thread_id=thread_id, timeout=timeout)


@council_app.command("retry", help="Re-query failed or missing members in a thread.")
def council_retry(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID (defaults to current).")] = None,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Per-model timeout in seconds.")] = None,
) -> None:
    """Re-query only the members that failed or didn't respond in the last round.

    Uses the original prompt from the most recent king message in the thread.
    """
    from kingdom.thread import get_thread, is_error_response, list_messages

    base = Path.cwd()
    feature = resolve_current_run(base)
    console = Console()

    # Resolve thread_id
    thread_id = resolve_council_thread_id(base, feature, thread_id, command="retry")

    meta = get_thread(base, feature, thread_id)
    all_members = {m for m in meta.members if m != "king"}
    messages = list_messages(base, feature, thread_id)

    # Find the most recent king message (the prompt to retry)
    last_king_msg = None
    for msg in messages:
        if msg.from_ == "king":
            last_king_msg = msg
    if last_king_msg is None:
        typer.echo('No king message found in thread. Send one first with `kd council ask "prompt"`.')
        raise typer.Exit(code=1)

    prompt = last_king_msg.body

    # Derive expected members from the last ask's target (not thread-level members)
    if last_king_msg.to == "all":
        expected = all_members
    else:
        # Single or comma-separated targets
        expected = {t.strip() for t in last_king_msg.to.split(",") if t.strip() != "king"} & all_members

    # Find members that responded successfully after the last ask
    ok_members: set[str] = set()
    for msg in messages:
        if msg.sequence > last_king_msg.sequence and msg.from_ in expected and not is_error_response(msg.body):
            ok_members.add(msg.from_)

    failed = expected - ok_members
    if not failed:
        typer.echo("All members responded successfully. Nothing to retry.")
        return

    # Set up council filtered to failed members only
    logs_dir = logs_root(base, feature)
    logs_dir.mkdir(parents=True, exist_ok=True)
    c = Council.create(logs_dir=logs_dir, base=base)
    if timeout is not None:
        c.timeout = timeout
    c.load_sessions(base, feature)
    c.members = [m for m in c.members if m.name in failed]

    if not c.members:
        typer.echo(f"Failed members ({', '.join(sorted(failed))}) not found in council config.")
        raise typer.Exit(code=1)

    member_names_str = ", ".join(m.name for m in c.members)
    console.print(f"[dim]Thread: {thread_id}[/dim]")
    console.print(f"[dim]Retrying: {member_names_str}[/dim]\n")

    def on_response(name, response):
        render_response(response, console)

    c.query_to_thread(prompt, base, feature, thread_id, callback=on_response)
    c.save_sessions(base, feature)


def render_response(response, console):
    """Render a single AgentResponse as Markdown."""
    if response.error:
        content = f"> **Error:** {response.error}\n\n"
        if response.text:
            content += response.text
        else:
            content += "*No response*"
    else:
        content = response.text if response.text else "*No response*"

    from kingdom.tui.widgets import format_elapsed

    console.print(Markdown(f"## {response.name}\n\n{content}"))
    console.print(f"[dim]{format_elapsed(response.elapsed)}[/dim]", justify="right")
    console.print()


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
        render_response(responses[name], console)

    console.print(f"[dim]Thread: {thread_id}[/dim]")


# ---------------------------------------------------------------------------
# kd chat — TUI council chat
# ---------------------------------------------------------------------------


@app.command(help="Open council chat TUI.")
def chat(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID to open.")] = None,
    new: Annotated[bool, typer.Option("--new", help="Create a new thread.")] = False,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="Preserve per-member stream NDJSON files as .debug-stream-*.jsonl in the thread directory.",
        ),
    ] = False,
    writable: Annotated[
        bool, typer.Option("--writable", "-w", help="Grant council members full write permissions.")
    ] = False,
) -> None:
    """Open the council chat TUI.

    Opens an existing thread, creates a new one, or lists recent threads.
    """
    from kingdom.config import load_config
    from kingdom.thread import create_thread, list_threads

    base = Path.cwd()
    feature = resolve_current_run(base)
    cfg = load_config(base)

    if new:
        tid = f"council-{secrets.token_hex(2)}"
        member_names = cfg.council.members or list(cfg.agents)
        create_thread(base, feature, tid, ["king", *member_names], "council")
        set_current_thread(base, feature, tid)
    elif thread_id:
        tid = thread_id
        from kingdom.thread import thread_dir

        if not thread_dir(base, feature, tid).exists():
            typer.echo(f"Thread not found: {tid}")
            raise typer.Exit(code=1)
    else:
        current = get_current_thread(base, feature)
        if current:
            from kingdom.thread import thread_dir

            if thread_dir(base, feature, current).exists():
                tid = current
            else:
                set_current_thread(base, feature, None)
                current = None

        if not current:
            threads = list_threads(base, feature)
            if threads:
                typer.echo("Recent threads:")
                for t in threads[-5:]:
                    created = t.created_at.strftime("%Y-%m-%d %H:%M")
                    members = ", ".join(m for m in t.members if m != "king")
                    typer.echo(f"  {t.id}  {created}  [{members}]")
                typer.echo()
                typer.echo("Usage: kd chat <thread-id>  or  kd chat --new")
            else:
                typer.echo("No threads found. Create one with: kd chat --new")
            raise typer.Exit(code=0)

    from kingdom.tui.app import ChatApp

    app_instance = ChatApp(base=base, branch=feature, thread_id=tid, debug_streams=debug, writable=writable)
    app_instance.run()


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
        typer.echo(f"Created design template at {design_path.relative_to(base)}")
        return

    typer.echo(f"Design already exists at {design_path.relative_to(base)}")


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
    typer.echo("Design approved")


@app.command(help="Draft or iterate the current breakdown.")
def breakdown() -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    _, design_path, breakdown_path, _ = get_branch_paths(base, feature)

    # Ensure breakdown template exists
    if not breakdown_path.exists() or not breakdown_path.read_text(encoding="utf-8").strip():
        breakdown_path.parent.mkdir(parents=True, exist_ok=True)
        breakdown_path.write_text(build_breakdown_template(feature), encoding="utf-8")

    design_rel = design_path.relative_to(base)

    prompt = "\n".join(
        [
            f"# Ticket Breakdown: {feature}",
            "",
            f"Read the design doc at `{design_rel}`, then create tickets for this branch.",
            "",
            "## Instructions",
            "",
            f"1. Read the design doc: `{design_rel}`",
            "2. For each work item, create a ticket:",
            '   `kd tk create "<title>" -p <priority>` (1=critical, 2=normal, 3=low)',
            "3. Edit each ticket file to add:",
            "   - A clear **problem statement** or context",
            "   - Specific **acceptance criteria** (checkboxes, not blank)",
            "4. Set dependencies between tickets where one must finish before another:",
            "   `kd tk dep <ticket-id> <depends-on-id>`",
            "5. Review the result: `kd tk list`",
            "",
            "## Guidelines",
            "",
            "- Set **priority** on every ticket (`-p 1` for blockers, `-p 2` for normal, `-p 3` for nice-to-have)",
            "- Identify **dependencies** — if ticket B can't start until ticket A is done, set `kd tk dep B A`",
            "- Write **meaningful acceptance criteria** — not empty checkboxes. Each criterion should be verifiable.",
            "- Keep tickets small and focused — one logical change per ticket",
        ]
    )

    typer.echo(prompt)


peasant_app = typer.Typer(name="peasant", help="Manage peasant agents.")
app.add_typer(peasant_app, name="peasant")


def worktree_path_for(base: Path, full_ticket_id: str) -> Path:
    """Return the canonical worktree path for a ticket (may not exist yet)."""
    return state_root(base) / "worktrees" / full_ticket_id


def create_worktree(base: Path, full_ticket_id: str) -> Path:
    """Create a git worktree for a ticket. Returns the worktree path."""
    worktree_path = worktree_path_for(base, full_ticket_id)

    if worktree_path.exists():
        return worktree_path

    worktrees_dir = worktree_path.parent
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    branch_name = f"ticket/{full_ticket_id}"

    # Check if branch exists
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True,
        text=True,
    )
    branch_exists = result.returncode == 0

    if branch_exists:
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        raise RuntimeError(f"Error creating worktree: {result.stderr.strip()}")

    # Run init-worktree.sh if it exists
    init_script = state_root(base) / "init-worktree.sh"
    if init_script.exists() and os.access(init_script, os.X_OK):
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
        pass

    return worktree_path


def remove_worktree(base: Path, full_ticket_id: str) -> None:
    """Remove a git worktree for a ticket."""
    worktree_path = worktree_path_for(base, full_ticket_id)

    if not worktree_path.exists():
        raise FileNotFoundError(f"No worktree found for {full_ticket_id}")

    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Error removing worktree: {result.stderr.strip()}")

    try:
        feature = resolve_current_run(base)
        _, state_path = get_design_paths(base, feature)
        state = read_json(state_path) if state_path.exists() else {}
        worktrees = state.get("worktrees", {})
        worktrees.pop(full_ticket_id, None)
        state["worktrees"] = worktrees
        write_json(state_path, state)
    except RuntimeError:
        pass


class PeasantContext(NamedTuple):
    """Resolved ticket and (optionally) feature branch for a peasant command."""

    base: Path
    ticket: Ticket
    ticket_path: Path
    full_ticket_id: str
    feature: str


def resolve_peasant_context(ticket_id: str, base: Path | None = None, auto_pull: bool = False) -> PeasantContext:
    """Resolve ticket and feature branch, or exit with an error message.

    Handles the repeated preamble shared by peasant_* commands:
    find_ticket + AmbiguousTicketMatch handling + resolve_current_run.

    Args:
        auto_pull: If True, move backlog tickets into the current branch.
            Only set for mutating commands (peasant start, kd work).
    """
    base = base or Path.cwd()

    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from None

    try:
        result = find_ticket(base, ticket_id, branch=feature)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    full_ticket_id = ticket.id

    # Auto-pull backlog tickets into the current branch (mutating commands only)
    if auto_pull and ticket_path.parent == backlog_root(base) / "tickets":
        ticket_path = move_ticket(ticket_path, branch_root(base, feature) / "tickets")

    return PeasantContext(
        base=base,
        ticket=ticket,
        ticket_path=ticket_path,
        full_ticket_id=full_ticket_id,
        feature=feature,
    )


def launch_work_background(
    base: Path,
    feature: str,
    ticket_id: str,
    agent: str,
    worktree_path: Path,
    thread_id: str,
    session_name: str,
) -> int:
    """Launch ``kd work`` as a background process.

    Builds the command, opens log file descriptors, spawns via Popen, and
    returns the child PID.  Used by ``peasant start`` and ``peasant review --reject``.
    """
    peasant_logs_dir = logs_root(base, feature) / session_name
    peasant_logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = peasant_logs_dir / "stdout.log"
    stderr_log = peasant_logs_dir / "stderr.log"

    work_cmd = [
        sys.executable,
        "-m",
        "kingdom.cli",
        "work",
        ticket_id,
        "--agent",
        agent,
        "--worktree",
        str(worktree_path),
        "--thread",
        thread_id,
        "--session",
        session_name,
        "--base",
        str(base),
    ]

    stdout_fd = os.open(str(stdout_log), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    stderr_fd = os.open(str(stderr_log), os.O_WRONLY | os.O_CREAT | os.O_APPEND)

    proc = subprocess.Popen(
        work_cmd,
        stdout=stdout_fd,
        stderr=stderr_fd,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    os.close(stdout_fd)
    os.close(stderr_fd)
    return proc.pid


@peasant_app.command("start", help="Launch a peasant agent on a ticket.")
def peasant_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID to work on.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent to use (default: from config).")] = None,
    hand: Annotated[bool, typer.Option("--hand", help="Run in current directory (serial mode).")] = False,
) -> None:
    """Create worktree, session, thread, and launch agent harness in background."""
    from kingdom.config import load_config
    from kingdom.session import update_agent_state
    from kingdom.thread import create_thread

    ctx = resolve_peasant_context(ticket_id, auto_pull=True)
    base, ticket, full_ticket_id, feature = ctx.base, ctx.ticket, ctx.full_ticket_id, ctx.feature

    # Block starting work on tickets that are in_review or closed
    if ticket.status in ("in_review", "closed"):
        typer.echo(f"Cannot start work on {full_ticket_id}: ticket is {ticket.status}")
        raise typer.Exit(code=1)

    # Transition open → in_progress
    if ticket.status == "open":
        ticket.status = "in_progress"
        write_ticket(ticket, ctx.ticket_path)

    # Default agent from config if not specified on CLI
    if agent is None:
        cfg = load_config(base)
        agent = cfg.peasant.agent

    session_name = f"peasant-{full_ticket_id}"
    thread_id = f"{full_ticket_id}-work"

    # Check if already running
    from kingdom.session import get_agent_state

    existing = get_agent_state(base, feature, session_name)
    if existing.status == "working" and existing.pid:
        # Check if process is actually alive
        try:
            os.kill(existing.pid, 0)
            typer.echo(f"Peasant already running on {full_ticket_id} (pid {existing.pid})")
            raise typer.Exit(code=1)
        except OSError:
            pass  # Process is dead, continue

    # 1. Create worktree (or use base if hand mode)
    if hand:
        # Guard: block if another peasant is already running on the same checkout
        from kingdom.session import list_active_agents

        for active in list_active_agents(base, feature):
            if active.name == session_name:
                continue  # already handled above
            if active.status == "working" and active.pid and active.name.startswith("peasant-"):
                try:
                    os.kill(active.pid, 0)
                    typer.echo(
                        f"Error: peasant {active.name} (pid {active.pid}) is already working "
                        f"on this checkout. Stop it first or use worktree mode."
                    )
                    raise typer.Exit(code=1)
                except OSError:
                    pass  # Process is dead, safe to continue
        worktree_path = base
        typer.echo(f"Running in hand mode (serial) on {base}")
    else:
        try:
            worktree_path = create_worktree(base, full_ticket_id)
        except RuntimeError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from None

    # Auto-assign ticket to the peasant session
    ticket.assignee = session_name
    write_ticket(ticket, ctx.ticket_path)

    # 2. Create work thread (ignore if already exists)
    with contextlib.suppress(FileExistsError):
        create_thread(base, feature, thread_id, [session_name, "king"], "work")

    # 3. Seed thread with ticket_start message
    from kingdom.thread import add_message, thread_dir

    tdir = thread_dir(base, feature, thread_id)
    # Only seed if no messages yet
    existing_msgs = list(tdir.glob("[0-9][0-9][0-9][0-9]-*.md"))
    if not existing_msgs:
        seed_body = f"# Starting work on {full_ticket_id}\n\n"
        seed_body += f"**Title:** {ticket.title}\n\n"
        seed_body += ticket.body
        add_message(base, feature, thread_id, from_="king", to=session_name, body=seed_body)

    # 4. Launch harness as background process
    pid = launch_work_background(base, feature, full_ticket_id, agent, worktree_path, thread_id, session_name)

    # 5. Update session with pid and status
    now = datetime.now(UTC).isoformat()
    update_agent_state(
        base,
        feature,
        session_name,
        status="working",
        pid=pid,
        ticket=full_ticket_id,
        thread=thread_id,
        agent_backend=agent,
        started_at=now,
        last_activity=now,
    )

    peasant_logs_dir = logs_root(base, feature) / session_name
    typer.echo(f"Started {session_name} (pid {pid})")
    typer.echo(f"  Agent: {agent}")
    typer.echo(f"  Ticket: {full_ticket_id}")
    typer.echo(f"  Worktree: {worktree_path}")
    typer.echo(f"  Thread: {thread_id}")
    typer.echo(f"  Logs: {peasant_logs_dir}")


@peasant_app.command("status", help="Show active peasants.")
def peasant_status() -> None:
    """Show table of active peasants: ticket, agent, status, elapsed, last activity."""

    from kingdom.session import list_active_agents

    base = Path.cwd()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from None

    console = Console()
    active = list_active_agents(base, feature)

    # Filter to peasant sessions only
    peasants = [a for a in active if a.name.startswith("peasant-")]

    if not peasants:
        typer.echo("No active peasants. Start one with `kd peasant start <ticket-id>`.")
        return

    table = Table(title="Active Peasants")
    table.add_column("Ticket", style="cyan")
    table.add_column("Agent")
    table.add_column("Status", style="bold")
    table.add_column("Elapsed")
    table.add_column("Last Activity")

    now = datetime.now(UTC)
    for p in peasants:
        ticket = p.ticket or p.name.replace("peasant-", "")

        # Calculate elapsed
        elapsed = ""
        if p.started_at:
            try:
                started = datetime.fromisoformat(p.started_at.replace("Z", "+00:00"))
                delta = now - started
                minutes = int(delta.total_seconds() / 60)
                elapsed = f"{minutes}m"
            except (ValueError, TypeError):
                elapsed = "?"

        # Format last activity
        last = ""
        if p.last_activity:
            try:
                last_dt = datetime.fromisoformat(p.last_activity.replace("Z", "+00:00"))
                ago = int((now - last_dt).total_seconds() / 60)
                last = f"{ago}m ago"
            except (ValueError, TypeError):
                last = "?"

        # Check if process is still alive
        display_status = p.status
        if p.pid and p.status == "working":
            try:
                os.kill(p.pid, 0)
            except OSError:
                display_status = "dead"

        # Color status
        status_style = {
            "working": "green",
            "blocked": "yellow",
            "done": "blue",
            "failed": "red",
            "stopped": "dim",
            "dead": "red",
        }.get(display_status, "")

        agent_display = p.agent_backend or "?"

        table.add_row(
            ticket,
            agent_display,
            f"[{status_style}]{display_status}[/{status_style}]" if status_style else display_status,
            elapsed,
            last,
        )

    console.print(table)


@peasant_app.command("logs", help="Show peasant logs.")
def peasant_logs(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Tail logs continuously.")] = False,
) -> None:
    """Show stdout/stderr logs for a peasant."""
    ctx = resolve_peasant_context(ticket_id)

    session_name = f"peasant-{ctx.full_ticket_id}"
    peasant_logs_dir = logs_root(ctx.base, ctx.feature) / session_name
    stdout_log = peasant_logs_dir / "stdout.log"
    stderr_log = peasant_logs_dir / "stderr.log"

    if not peasant_logs_dir.exists():
        typer.echo(f"No logs found for {ctx.full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1)

    if follow:
        # Tail both stdout and stderr
        with contextlib.suppress(KeyboardInterrupt):
            files = [str(f) for f in [stdout_log, stderr_log] if f.exists()]
            if files:
                subprocess.run(["tail", "-f", *files])
            else:
                typer.echo("Log files are empty. The peasant may still be starting up.")
        return

    # Show both stdout and stderr
    console = Console()

    if stdout_log.exists() and stdout_log.stat().st_size > 0:
        content = stdout_log.read_text(encoding="utf-8")
        console.print(Markdown(f"## stdout\n\n```\n{content}\n```"))

    if stderr_log.exists() and stderr_log.stat().st_size > 0:
        content = stderr_log.read_text(encoding="utf-8")
        console.print(Markdown(f"## stderr\n\n```\n{content}\n```"))

    if not (stdout_log.exists() or stderr_log.exists()):
        typer.echo("Log files are empty. The peasant may still be starting up.")


@peasant_app.command("stop", help="Stop a running peasant.")
def peasant_stop(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Send SIGTERM to the peasant process and update status to stopped."""
    from kingdom.session import get_agent_state, update_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    session_name = f"peasant-{full_ticket_id}"
    state = get_agent_state(base, feature, session_name)

    if state.status != "working":
        typer.echo(f"Peasant {full_ticket_id} is not running (status: {state.status})")
        raise typer.Exit(code=1)

    if not state.pid:
        typer.echo(f"No PID found for peasant {full_ticket_id}")
        raise typer.Exit(code=1)

    # Send SIGTERM
    try:
        os.kill(state.pid, signal.SIGTERM)
        typer.echo(f"{full_ticket_id}: sent SIGTERM (pid {state.pid})")
    except OSError as e:
        typer.echo(f"Process {state.pid} not found: {e}")

    # Update session status
    now = datetime.now(UTC).isoformat()
    update_agent_state(
        base,
        feature,
        session_name,
        status="stopped",
        last_activity=now,
    )
    typer.echo("Status updated to stopped")


@peasant_app.command("clean", help="Remove a peasant's worktree.")
def peasant_clean(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Remove the git worktree for a ticket."""
    ctx = resolve_peasant_context(ticket_id)

    try:
        remove_worktree(ctx.base, ctx.full_ticket_id)
        typer.echo(f"{ctx.full_ticket_id}: worktree removed")
    except FileNotFoundError:
        typer.echo(f"No worktree found for {ctx.full_ticket_id}")
        raise typer.Exit(code=1) from None
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from None


@peasant_app.command("sync", help="Pull parent branch changes into a peasant's worktree.")
def peasant_sync(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Merge the parent branch into the worktree's ticket branch, then refresh dependencies."""
    from kingdom.session import get_agent_state

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    # Refuse if peasant is actively running
    session_name = f"peasant-{full_ticket_id}"
    state = get_agent_state(base, feature, session_name)
    if state.status == "working" and state.pid:
        try:
            os.kill(state.pid, 0)
            typer.echo(
                f"Peasant is running on {full_ticket_id} (pid {state.pid}). Stop it first with `kd peasant stop`."
            )
            raise typer.Exit(code=1)
        except OSError:
            pass  # Process is dead, safe to sync

    # Find worktree
    worktree_path = worktree_path_for(base, full_ticket_id)
    if not worktree_path.exists():
        typer.echo(f"No worktree found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1)

    # Merge parent branch into worktree
    parent_branch = feature
    typer.echo(f"Merging {parent_branch} into worktree for {full_ticket_id}...")
    merge_result = subprocess.run(
        ["git", "merge", parent_branch, "--no-edit"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )

    if merge_result.returncode != 0:
        # Check for merge conflict
        typer.echo("Merge failed.")
        if merge_result.stdout.strip():
            typer.echo(merge_result.stdout.strip())
        if merge_result.stderr.strip():
            typer.echo(merge_result.stderr.strip())
        # Abort the merge so we don't leave the worktree in a dirty state
        subprocess.run(["git", "merge", "--abort"], capture_output=True, cwd=worktree_path)
        typer.echo(f"\nMerge aborted. To resolve manually:\n  cd {worktree_path}\n  git merge {parent_branch}")
        raise typer.Exit(code=1)

    if merge_result.stdout.strip():
        typer.echo(merge_result.stdout.strip())

    # Run init-worktree.sh to refresh dependencies
    init_script = state_root(base) / "init-worktree.sh"
    if init_script.exists() and os.access(init_script, os.X_OK):
        typer.echo("Running init-worktree.sh...")
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

    typer.echo(f"{full_ticket_id}: sync complete")


@peasant_app.command("msg", help="Send a directive to a working peasant.")
def peasant_msg(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    message: Annotated[str, typer.Argument(help="Directive message for the peasant.")],
) -> None:
    """Write a directive to the work thread; the peasant picks it up on next loop iteration."""
    from kingdom.thread import add_message

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    thread_id = f"{full_ticket_id}-work"

    try:
        add_message(base, feature, thread_id, from_="king", to=f"peasant-{full_ticket_id}", body=message)
    except FileNotFoundError:
        typer.echo(f"No work thread found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1) from None

    typer.echo(f"{full_ticket_id}: directive sent")

    # Warn if peasant is not running
    from kingdom.session import get_agent_state

    session_name = f"peasant-{full_ticket_id}"
    state = get_agent_state(base, feature, session_name)
    process_alive = False
    if state.status == "working" and state.pid:
        try:
            os.kill(state.pid, 0)
            process_alive = True
        except OSError:
            pass
    if not process_alive:
        typer.echo(
            f"Warning: peasant is not running (status: {state.status}). Message won't be picked up until restarted."
        )


@peasant_app.command("read", help="Show messages from a peasant.")
def peasant_read(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    last: Annotated[int, typer.Option("--last", "-n", help="Number of messages to show.", min=1)] = 10,
) -> None:
    """Show recent messages from the peasant (escalations, status updates)."""
    from kingdom.thread import list_messages

    ctx = resolve_peasant_context(ticket_id)
    base, full_ticket_id, feature = ctx.base, ctx.full_ticket_id, ctx.feature

    thread_id = f"{full_ticket_id}-work"
    session_name = f"peasant-{full_ticket_id}"

    try:
        messages = list_messages(base, feature, thread_id)
    except FileNotFoundError:
        typer.echo(f"No work thread found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1) from None

    # Filter to messages from the peasant
    peasant_msgs = [m for m in messages if m.from_ == session_name]

    if not peasant_msgs:
        typer.echo(f"No messages from {session_name} yet. The peasant may still be working.")
        return

    # Show last N messages
    console = Console()
    for msg in peasant_msgs[-last:]:
        ts = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        header = f"## [{ts}] {msg.from_} → {msg.to}"
        console.print(Markdown(f"{header}\n\n{msg.body}"))


@peasant_app.command("review", help="Review a peasant's completed work.")
def peasant_review(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    accept: Annotated[bool, typer.Option("--accept", help="Accept the work (close ticket).")] = False,
    reject: Annotated[str | None, typer.Option("--reject", help="Reject with feedback message.")] = None,
) -> None:
    """Run pytest + ruff, show diff and worklog. Accept or reject the work."""
    from kingdom.harness import extract_worklog
    from kingdom.session import get_agent_state, update_agent_state
    from kingdom.thread import add_message

    ctx = resolve_peasant_context(ticket_id)
    base, ticket, ticket_path = ctx.base, ctx.ticket, ctx.ticket_path
    full_ticket_id, feature = ctx.full_ticket_id, ctx.feature

    session_name = f"peasant-{full_ticket_id}"
    thread_id = f"{full_ticket_id}-work"
    branch_name = f"ticket/{full_ticket_id}"

    console = Console()

    # --- Accept / Reject actions ---
    if accept and reject is not None:
        print_error("--accept and --reject are mutually exclusive.")
        raise typer.Exit(code=1)

    if accept:
        ticket.status = "closed"
        write_ticket(ticket, ticket_path)
        update_agent_state(
            base,
            feature,
            session_name,
            status="done",
            last_activity=datetime.now(UTC).isoformat(),
        )
        typer.echo(f"{full_ticket_id}: accepted — ticket closed")
        return

    if reject is not None:
        try:
            add_message(base, feature, thread_id, from_="king", to=session_name, body=reject)
        except FileNotFoundError:
            typer.echo(
                f"No work thread found for {full_ticket_id}. Start one with `kd peasant start {full_ticket_id}`."
            )
            raise typer.Exit(code=1) from None

        # Check if peasant process is still alive
        state = get_agent_state(base, feature, session_name)
        process_alive = False
        if state.status == "working" and state.pid:
            try:
                os.kill(state.pid, 0)
                process_alive = True
            except OSError:
                pass

        if process_alive:
            update_agent_state(
                base,
                feature,
                session_name,
                status="working",
                last_activity=datetime.now(UTC).isoformat(),
            )
            typer.echo(f"{full_ticket_id}: rejected — feedback sent, peasant will pick it up")
        else:
            # Relaunch the harness
            agent_backend = state.agent_backend or "claude"
            worktree_path = worktree_path_for(base, full_ticket_id)
            if not worktree_path.exists():
                print_error(f"worktree missing for {full_ticket_id}. Run `kd peasant start` to recreate.")
                raise typer.Exit(code=1)

            pid = launch_work_background(
                base, feature, full_ticket_id, agent_backend, worktree_path, thread_id, session_name
            )

            now = datetime.now(UTC).isoformat()
            update_agent_state(
                base,
                feature,
                session_name,
                status="working",
                pid=pid,
                last_activity=now,
            )
            typer.echo(f"{full_ticket_id}: rejected — feedback sent, peasant relaunched (pid {pid})")
        return

    # --- Show review info ---

    # 1. Run pytest
    worktree_path = worktree_path_for(base, full_ticket_id)
    if worktree_path.exists():
        test_cwd = str(worktree_path)
    else:
        test_cwd = str(base)

    typer.echo("Running pytest...")
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=test_cwd,
    )
    test_passed = test_result.returncode == 0
    test_output = test_result.stdout.strip()
    if test_result.stderr.strip():
        test_output += "\n" + test_result.stderr.strip()

    test_title = "pytest: PASSED" if test_passed else "pytest: FAILED"
    test_content = test_output or "(no output)"
    console.print(Markdown(f"## {test_title}\n\n```\n{test_content}\n```"))

    # 2. Run ruff
    typer.echo("Running ruff...")
    ruff_result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=test_cwd,
    )
    ruff_passed = ruff_result.returncode == 0
    ruff_output = ruff_result.stdout.strip()
    if ruff_result.stderr.strip():
        ruff_output += "\n" + ruff_result.stderr.strip()

    ruff_title = "ruff: PASSED" if ruff_passed else "ruff: ISSUES"
    ruff_content = ruff_output or "All checks passed!"
    console.print(Markdown(f"## {ruff_title}\n\n```\n{ruff_content}\n```"))

    # 3. Show diff
    diff_result = subprocess.run(
        ["git", "diff", f"HEAD...{branch_name}", "--stat"],
        capture_output=True,
        text=True,
        cwd=str(base),
    )
    diff_output = diff_result.stdout.strip()
    diff_err = diff_result.stderr.strip()
    if diff_result.returncode != 0 and diff_err:
        console.print(Markdown(f"## diff error: HEAD...{branch_name}\n\n```\n{diff_err}\n```"))
    elif diff_output:
        console.print(Markdown(f"## diff: HEAD...{branch_name}\n\n```\n{diff_output}\n```"))
    else:
        typer.echo("(no diff — branch may not have diverged yet)")

    # 4. Show worklog
    worklog = extract_worklog(ticket_path)
    if worklog:
        console.print(Markdown(f"## Worklog\n\n{worklog}"))
    else:
        typer.echo("(no worklog entries)")

    # 5. Show session status
    state = get_agent_state(base, feature, session_name)
    typer.echo(f"\nPeasant status: {state.status}")

    # Prompt for action
    all_passed = test_passed and ruff_passed
    if all_passed:
        typer.echo("\nAll checks passed. Use --accept to close the ticket or --reject 'feedback' to send feedback.")
    else:
        typer.echo("\nSome checks failed. Use --reject 'feedback' to send feedback.")


@app.command("work", help="Run autonomous agent loop on a ticket.")
def work(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent name (default: from config).")] = None,
    worktree: Annotated[str | None, typer.Option("--worktree", help="Worktree path (internal).")] = None,
    thread: Annotated[str | None, typer.Option("--thread", help="Thread ID (internal).")] = None,
    session: Annotated[str | None, typer.Option("--session", help="Session name (internal).")] = None,
    base_dir: Annotated[str, typer.Option("--base", help="Project root.")] = ".",
) -> None:
    """Run the autonomous agent harness loop.

    Can be run directly (foreground) or via `kd peasant start` (background).
    If run directly, it works in the current directory.
    """
    import logging

    from kingdom.config import load_config
    from kingdom.harness import run_agent_loop

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    base = Path(base_dir).resolve()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from None

    # Default agent from config if not specified on CLI
    if agent is None:
        cfg = load_config(base)
        agent = cfg.peasant.agent

    # Resolve ticket context if not provided (interactive mode)
    if not (worktree and thread and session):
        ctx = resolve_peasant_context(ticket_id, base=base, auto_pull=True)
        # In interactive mode, we are the session
        session = session or f"hand-{ctx.full_ticket_id}"
        thread = thread or f"{ctx.full_ticket_id}-work"
        worktree = worktree or str(Path.cwd())
        # Ensure thread exists
        from kingdom.thread import add_message, create_thread, thread_dir

        with contextlib.suppress(FileExistsError):
            create_thread(base, feature, thread, [session, "king"], "work")

        # Seed thread with ticket content (same as peasant_start)
        tdir = thread_dir(base, feature, thread)
        existing_msgs = list(tdir.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if not existing_msgs:
            seed_body = f"# Starting work on {ctx.full_ticket_id}\n\n"
            seed_body += f"**Title:** {ctx.ticket.title}\n\n"
            seed_body += ctx.ticket.body
            add_message(base, feature, thread, from_="king", to=session, body=seed_body)

    worktree_path = Path(worktree).resolve()

    status = run_agent_loop(
        base=base,
        branch=feature,
        agent_name=agent,
        ticket_id=ticket_id,
        worktree=worktree_path,
        thread_id=thread,
        session_name=session,
    )

    if status != "done":
        raise typer.Exit(code=1)


@app.command(help="Reserved for broader develop phase (MVP stub).")
def dev(ticket: str | None = typer.Argument(None, help="Optional ticket id.")) -> None:
    if ticket:
        typer.echo("MVP uses `kd peasant start <ticket>` for single-ticket execution.")
        raise typer.Exit(code=1)
    typer.echo("`kd dev` is reserved. Use `kd peasant start <ticket>` in the MVP.")


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


def check_cli(command: list[str]) -> tuple[bool, str | None]:
    """Check if a CLI command is available."""
    try:
        subprocess.run(command, capture_output=True, timeout=5)
        return (True, None)
    except FileNotFoundError:
        return (False, "Command not found")
    except subprocess.TimeoutExpired:
        return (False, "Command timed out")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

config_app = typer.Typer(name="config", help="View and manage configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show", help="Print the effective configuration.")
def config_show() -> None:
    """Print the merged config (defaults + user overrides) as JSON."""
    import dataclasses

    from kingdom.config import load_config

    base = Path.cwd()
    try:
        cfg = load_config(base)
    except ValueError as e:
        typer.secho(f"Error: invalid config — {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    def strip_empty(obj: object) -> object:
        if isinstance(obj, dict):
            return {k: v for k, v in ((k, strip_empty(v)) for k, v in obj.items()) if v not in ("", [], {}, None)}
        if isinstance(obj, list):
            return [strip_empty(item) for item in obj]
        return obj

    console = Console()
    console.print_json(json.dumps(strip_empty(dataclasses.asdict(cfg)), indent=2))


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


def get_doctor_checks(base: Path) -> list[dict[str, str | list[str]]]:
    """Build doctor checks from agent configs."""
    import shlex

    from kingdom.agent import resolve_all_agents
    from kingdom.config import load_config

    cfg = load_config(base)
    agents = resolve_all_agents(cfg.agents)

    checks: list[dict[str, str | list[str]]] = []
    for agent in agents.values():
        version_cmd = agent.version_command or f"{shlex.split(agent.cli)[0]} --version"
        checks.append(
            {
                "name": agent.name,
                "command": shlex.split(version_cmd),
                "install_hint": agent.install_hint or f"Install {agent.name}",
            }
        )
    return checks


def check_config(base: Path) -> tuple[bool, str | None]:
    """Validate .kd/config.json and return (ok, error_message).

    Returns (True, None) if config is valid or doesn't exist.
    Returns (False, message) if config has errors.
    """
    from kingdom.config import load_config
    from kingdom.state import state_root

    config_path = state_root(base) / "config.json"
    if not config_path.exists():
        return True, None

    try:
        load_config(base)
        return True, None
    except ValueError as e:
        return False, str(e)


@app.command(help="Check config and agent CLIs.")
def doctor(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Validate config and verify agent CLIs are installed."""
    from kingdom.state import state_root

    base = Path.cwd()
    has_issues = False

    # 1. Config validation
    config_path = state_root(base) / "config.json"
    config_ok, config_error = check_config(base)

    if not config_ok:
        has_issues = True

    if output_json:
        config_result = {"exists": config_path.exists(), "valid": config_ok, "error": config_error}
    else:
        typer.echo("\nConfig:")
        if not config_path.exists():
            typer.secho("  ○ No config.json (using defaults)", fg=typer.colors.YELLOW)
        elif config_ok:
            typer.secho("  ✓ config.json valid", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  ✗ config.json: {config_error}", fg=typer.colors.RED)

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
            typer.secho("  ○ Skipped (fix config first)", fg=typer.colors.YELLOW)
        else:
            typer.echo("\nAgent CLIs:")
            for check in doctor_checks:
                name = check["name"]
                result = cli_results[name]
                if result["installed"]:
                    typer.secho(f"  ✓ {name:12} (installed)", fg=typer.colors.GREEN)
                else:
                    typer.secho(f"  ✗ {name:12} (not found)", fg=typer.colors.RED)

            if cli_issues:
                typer.echo("\nIssues found:")
                for issue in cli_issues:
                    typer.echo(f"  {issue['name']}: {issue['hint']}")
        typer.echo()

    if has_issues or cli_issues:
        raise typer.Exit(code=1)


@app.command(help="Print the current agent's role and name.")
def whoami() -> None:
    """Identify the current agent role via KD_ROLE and KD_AGENT_NAME env vars."""
    import os

    role = os.environ.get("KD_ROLE", "")
    agent_name = os.environ.get("KD_AGENT_NAME", "")

    if not role:
        role = "hand" if os.environ.get("CLAUDECODE") else "king"

    if agent_name:
        typer.echo(f"{role}: {agent_name}")
    else:
        typer.echo(role)


@app.command(help="Migrate legacy kin-XXXX ticket IDs to short XXXX format.")
def migrate(
    apply: Annotated[bool, typer.Option("--apply", help="Apply changes (default is dry-run).")] = False,
) -> None:
    """Rename ticket files and rewrite frontmatter IDs, deps, and parent refs to drop 'kin-' prefix.

    By default shows what would change (dry-run). Use --apply to execute.
    """
    import re

    base = Path.cwd()
    dry_run = not apply

    # Collect all ticket files across backlog, branches, and archive
    ticket_dirs: list[Path] = []

    backlog_tickets = backlog_root(base) / "tickets"
    if backlog_tickets.exists():
        ticket_dirs.append(backlog_tickets)

    bdir = branches_root(base)
    if bdir.exists():
        for branch_dir in bdir.iterdir():
            if branch_dir.is_dir():
                td = branch_dir / "tickets"
                if td.exists():
                    ticket_dirs.append(td)

    adir = archive_root(base)
    if adir.exists():
        for archive_item in adir.iterdir():
            if archive_item.is_dir():
                td = archive_item / "tickets"
                if td.exists():
                    ticket_dirs.append(td)

    renamed = 0
    rewritten = 0
    collisions: list[str] = []

    # Preflight: check for collisions before any renames
    for td in ticket_dirs:
        for ticket_file in sorted(td.glob("kin-*.md")):
            new_name = ticket_file.name[4:]  # Remove "kin-" prefix
            new_path = ticket_file.parent / new_name
            if new_path.exists():
                collisions.append(str(ticket_file.relative_to(base)))

    if collisions:
        print_error("collision detected — target files already exist:")
        for c in collisions:
            error_console.print(f"  {c}")
        raise typer.Exit(code=1)

    # Pass 1: rename files (git mv for history preservation)
    for td in ticket_dirs:
        for ticket_file in sorted(td.glob("kin-*.md")):
            new_name = ticket_file.name[4:]
            new_path = ticket_file.parent / new_name

            if dry_run:
                typer.echo(f"  rename: {ticket_file.relative_to(base)} → {new_name}")
            else:
                # Use git mv if in a git repo, fall back to plain rename
                result = subprocess.run(
                    ["git", "mv", str(ticket_file), str(new_path)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    ticket_file.rename(new_path)
                renamed += 1

    # Pass 2: rewrite frontmatter in all ticket files
    for td in ticket_dirs:
        for ticket_file in sorted(td.glob("*.md")):
            content = ticket_file.read_text(encoding="utf-8")
            new_content = re.sub(r"\bkin-([0-9a-f]{4})\b", r"\1", content)
            if new_content != content:
                if dry_run:
                    typer.echo(f"  rewrite: {ticket_file.relative_to(base)}")
                else:
                    ticket_file.write_text(new_content, encoding="utf-8")
                    rewritten += 1

    if dry_run:
        typer.echo("\nDry run complete. Run with --apply to execute.")
    else:
        typer.echo(f"Migrated {renamed} files renamed, {rewritten} files rewritten")


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
    dep: Annotated[list[str] | None, typer.Option("--dep", help="Ticket ID(s) this depends on.")] = None,
) -> None:
    """Create a new ticket in the current branch or backlog."""
    from datetime import datetime

    base = Path.cwd()

    # Validate priority range (1-3)
    if priority < 1 or priority > 3:
        sys.stderr.write(f"Warning: Priority {priority} outside valid range (1-3), clamping.\n")
        priority = max(1, min(3, priority))

    # Ensure base layout exists
    ensure_base_layout(base)

    tickets_dir = get_tickets_dir(base, backlog=backlog)
    tickets_dir.mkdir(parents=True, exist_ok=True)

    # Resolve dependency IDs
    resolved_deps: list[str] = []
    if dep:
        for dep_id in dep:
            try:
                dep_result = find_ticket(base, dep_id)
            except AmbiguousTicketMatch as e:
                print_error(f"{e}")
                raise typer.Exit(code=1) from None
            if dep_result is None:
                typer.echo(f"Dependency ticket not found: {dep_id}")
                raise typer.Exit(code=1)
            resolved_deps.append(dep_result[0].id)

    # Generate unique ID
    ticket_id = generate_ticket_id(tickets_dir)

    # Build body with acceptance criteria section
    body = description or ""
    if not body:
        body = "## Acceptance Criteria\n\n- [ ]"

    # Create ticket
    ticket = Ticket(
        id=ticket_id,
        status="open",
        deps=resolved_deps,
        links=[],
        created=datetime.now(UTC),
        type=ticket_type,
        priority=priority,
        title=title,
        body=body,
    )

    ticket_path = tickets_dir / f"{ticket_id}.md"
    write_ticket(ticket, ticket_path)

    dep_suffix = f" (depends on: {', '.join(resolved_deps)})" if resolved_deps else ""
    location_label = " (backlog)" if backlog else ""
    typer.echo(f"Created {ticket_id}{location_label}: {title}{dep_suffix}")
    typer.echo(str(ticket_path))


def format_ticket_summary(tickets: list) -> str:
    """Build a one-line summary of ticket counts by status.

    Args:
        tickets: List of Ticket objects (or dicts with 'status' key).

    Returns:
        A string like "5 open · 2 in_progress · 3 closed · 10 total".
    """
    counts: Counter[str] = Counter()
    for t in tickets:
        st = t["status"] if isinstance(t, dict) else t.status
        counts[st] += 1
    total = len(tickets)
    # Fixed display order
    parts = []
    for label in ("open", "in_progress", "in_review", "closed"):
        if counts[label]:
            parts.append(f"{counts[label]} {label}")
    parts.append(f"{total} total")
    return " · ".join(parts)


def format_ticket_line(ticket: Ticket, location: str | None = None) -> str:
    """Format a single ticket as a one-line string for list output.

    Includes dependency arrows when the ticket has deps, e.g.:
        a1b2 [P2][open] - My ticket  <- c3d4, e5f6

    Args:
        ticket: The ticket to format.
        location: Optional location label (e.g. "backlog", "branch:main").

    Returns:
        Formatted ticket line string.
    """
    assignee_str = f" @{ticket.assignee}" if ticket.assignee else ""
    location_str = f" ({location})" if location else ""
    dep_str = f"  <- {', '.join(ticket.deps)}" if ticket.deps else ""
    return f"{ticket.id} [P{ticket.priority}][{ticket.status}]{assignee_str} - {ticket.title}{location_str}{dep_str}"


def console_width() -> int:
    """Get the current terminal width, defaulting to 120 if unavailable."""
    try:
        return os.get_terminal_size().columns
    except (ValueError, OSError):
        return 120


STATUS_STYLES = {
    "open": "green",
    "in_progress": "yellow",
    "in_review": "magenta",
    "closed": "dim",
}


def render_ticket_table(
    tickets: list[Ticket],
    *,
    show_location: bool = False,
    locations: dict[str, str] | None = None,
) -> None:
    """Render a list of tickets as a Rich table.

    Only shows Assignee, Deps, and Location columns when at least one ticket
    has data for that column, keeping the table compact.

    Args:
        tickets: Tickets to display.
        show_location: Whether to include a Location column.
        locations: Mapping of ticket id -> location label (used with show_location).
    """
    has_assignee = any(t.assignee for t in tickets)
    has_deps = any(t.deps for t in tickets)

    console = Console(width=max(console_width(), 120))
    table = Table(show_header=True, header_style="bold", padding=(0, 1))

    table.add_column("ID", style="cyan", no_wrap=True, min_width=4)
    table.add_column("P", justify="center", no_wrap=True, min_width=2)
    table.add_column("Status", no_wrap=True, min_width=11)
    if has_assignee:
        table.add_column("Assignee", no_wrap=True)
    table.add_column("Title")
    if has_deps:
        table.add_column("Deps", style="dim", no_wrap=True)
    if show_location:
        table.add_column("Location", no_wrap=True)

    for ticket in tickets:
        status_style = STATUS_STYLES.get(ticket.status, "")
        dep_str = ", ".join(ticket.deps) if ticket.deps else ""
        assignee_str = f"@{ticket.assignee}" if ticket.assignee else ""

        row: list[str] = [
            ticket.id,
            f"P{ticket.priority}",
            f"[{status_style}]{ticket.status}[/{status_style}]" if status_style else ticket.status,
        ]
        if has_assignee:
            row.append(assignee_str)
        row.append(ticket.title)
        if has_deps:
            row.append(dep_str)
        if show_location:
            loc = (locations or {}).get(ticket.id, "")
            row.append(loc)

        table.add_row(*row)

    console.print(table)


@ticket_app.command("ls", help="List tickets.", hidden=True)
@ticket_app.command("list", help="List tickets.")
def ticket_list(
    all_tickets: Annotated[bool, typer.Option("--all", "-a", help="List all tickets across all locations.")] = False,
    include_done: Annotated[
        bool, typer.Option("--include-done", help="Include tickets from done branches (with --all).")
    ] = False,
    include_closed: Annotated[bool, typer.Option("--include-closed", help="Include closed tickets in output.")] = False,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            "-s",
            help="Filter by status (open, in_progress, in_review, closed). Overrides --include-closed.",
        ),
    ] = None,
    backlog: Annotated[bool, typer.Option("--backlog", help="List open tickets in backlog only.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """List tickets in the current branch or all locations."""
    if status is not None:
        status = status.lower()
        if status not in STATUSES:
            typer.echo(f"Invalid status '{status}'. Valid statuses: {', '.join(sorted(STATUSES))}")
            raise typer.Exit(code=1)

    def apply_status_filter(tickets: list) -> list:
        """Filter tickets based on --status or --include-closed flags."""
        if status is not None:
            return [t for t in tickets if t.status == status]
        if not include_closed:
            return [t for t in tickets if t.status != "closed"]
        return tickets

    base = Path.cwd()

    if backlog:
        backlog_dir = backlog_root(base) / "tickets"
        all_backlog_tickets = list_tickets(backlog_dir) if backlog_dir.exists() else []
        tickets = apply_status_filter(all_backlog_tickets)

        if output_json:
            results = [
                {
                    "id": t.id,
                    "priority": t.priority,
                    "status": t.status,
                    "title": t.title,
                    "deps": t.deps,
                    "location": "backlog",
                }
                for t in tickets
            ]
            typer.echo(json.dumps(results, indent=2))
        else:
            if not tickets:
                typer.echo('No backlog tickets. Create one with `kd tk create --backlog "title"`.')
                return
            render_ticket_table(tickets)
            typer.echo(format_ticket_summary(all_backlog_tickets))
        return

    if all_tickets:
        # Collect tickets from all locations
        locations: list[tuple[str, Path]] = []

        # branches/*/tickets/
        branches_dir = branches_root(base)
        if branches_dir.exists():
            for branch_dir in branches_dir.iterdir():
                if branch_dir.is_dir() and (include_done or not is_branch_done(branch_dir)):
                    tickets_dir = branch_dir / "tickets"
                    if tickets_dir.exists():
                        locations.append((f"branch:{branch_dir.name}", tickets_dir))

        # backlog/tickets/
        backlog_tickets = backlog_root(base) / "tickets"
        if backlog_tickets.exists():
            locations.append(("backlog", backlog_tickets))

        all_filtered: list[Ticket] = []
        all_unfiltered: list[Ticket] = []
        location_map: dict[str, str] = {}
        for location_name, tickets_dir in locations:
            tickets = list_tickets(tickets_dir)
            all_unfiltered.extend(tickets)
            filtered = apply_status_filter(tickets)
            for ticket in filtered:
                location_map[ticket.id] = location_name
            all_filtered.extend(filtered)

        if output_json:
            results = [
                {
                    "id": t.id,
                    "priority": t.priority,
                    "status": t.status,
                    "title": t.title,
                    "deps": t.deps,
                    "location": location_map.get(t.id, ""),
                }
                for t in all_filtered
            ]
            typer.echo(json.dumps(results, indent=2))
        else:
            if not all_filtered:
                typer.echo('No tickets found across any branch or backlog. Create one with `kd tk create "title"`.')
                return
            render_ticket_table(all_filtered, show_location=True, locations=location_map)
            typer.echo(format_ticket_summary(all_unfiltered))
    else:
        # List tickets for current branch only
        tickets_dir = get_tickets_dir(base)
        all_branch_tickets = list_tickets(tickets_dir)
        tickets = apply_status_filter(all_branch_tickets)

        if output_json:
            results = [
                {
                    "id": t.id,
                    "priority": t.priority,
                    "status": t.status,
                    "title": t.title,
                    "deps": t.deps,
                }
                for t in tickets
            ]
            typer.echo(json.dumps(results, indent=2))
        else:
            if not tickets:
                typer.echo('No tickets found. Create one with `kd tk create "title"`.')
                return
            render_ticket_table(tickets)
            typer.echo(format_ticket_summary(all_branch_tickets))


def resolve_dep_status(base: Path, dep_id: str) -> str:
    """Look up a dependency ticket's status by its ID.

    Args:
        base: Project root directory.
        dep_id: Full or partial ticket ID.

    Returns:
        The ticket's status string, or "unknown" if the ticket can't be found.
    """
    try:
        result = find_ticket(base, dep_id)
    except AmbiguousTicketMatch:
        return "unknown"
    if result is None:
        return "unknown"
    dep_ticket, _ = result
    return dep_ticket.status


STATUS_COLORS = {"open": "yellow", "in_progress": "cyan", "in_review": "magenta", "closed": "green"}


def render_ticket_panel(ticket: Ticket, ticket_path: Path, base: Path) -> Panel:
    """Build a Rich Panel displaying a ticket's metadata and body.

    Args:
        ticket: The Ticket dataclass instance.
        ticket_path: Absolute path to the ticket file.
        base: Project root directory (used for relative path display and dep lookups).

    Returns:
        A Rich Panel renderable.
    """
    # Metadata table (borderless grid)
    meta = Table.grid(padding=(0, 2))
    meta.add_column("label", style="dim", no_wrap=True)
    meta.add_column("value")

    status_color = STATUS_COLORS.get(ticket.status, "white")
    meta.add_row("status", f"[{status_color}]{ticket.status}[/{status_color}]")
    meta.add_row("priority", f"P{ticket.priority}")
    meta.add_row("type", ticket.type)
    meta.add_row("created", ticket.created.strftime("%Y-%m-%d"))

    if ticket.assignee:
        meta.add_row("assignee", ticket.assignee)

    if ticket.deps:
        dep_parts = []
        for dep_id in ticket.deps:
            dep_status = resolve_dep_status(base, dep_id)
            dep_color = STATUS_COLORS.get(dep_status, "white")
            dep_parts.append(f"{dep_id} [{dep_color}]{dep_status}[/{dep_color}]")
        meta.add_row("deps", ", ".join(dep_parts))

    if ticket.links:
        meta.add_row("links", ", ".join(ticket.links))

    # Build body content (markdown)
    parts: list[object] = [meta]
    if ticket.body.strip():
        parts.append(Text())  # blank line separator
        parts.append(Markdown(ticket.body))

    subtitle = str(ticket_path.relative_to(base))
    return Panel(
        Group(*parts),
        title=f"[bold]{ticket.id}[/bold]  {ticket.title}",
        subtitle=f"[dim]{subtitle}[/dim]",
        border_style="dim",
        padding=(1, 2),
    )


@ticket_app.command("show", help="Show a ticket.")
def ticket_show(
    ticket_ids: Annotated[
        list[str] | None, typer.Argument(help="Ticket ID(s) (full or partial). Omit to show ticket assigned to 'hand'.")
    ] = None,
    all_tickets: Annotated[bool, typer.Option("--all", "-a", help="Show all tickets on the current branch.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Display one or more tickets by ID (supports partial matching). With no args, shows ticket assigned to 'hand'."""
    base = Path.cwd()

    # Resolve tickets to show as (Ticket, Path) pairs
    pairs: list[tuple[Ticket, Path]] = []

    if all_tickets:
        try:
            feature = resolve_current_run(base)
        except RuntimeError:
            typer.echo("No active session. Use `kd start` first.")
            raise typer.Exit(code=1) from None
        tickets_dir = branch_root(base, feature) / "tickets"
        if tickets_dir.exists():
            for ticket_file in sorted(tickets_dir.glob("*.md")):
                with contextlib.suppress(ValueError, FileNotFoundError):
                    pairs.append((read_ticket(ticket_file), ticket_file))
        if not pairs:
            typer.echo('No tickets on this branch. Create one with `kd tk create "title"`.')
            raise typer.Exit(code=0)
    elif ticket_ids:
        for tid in ticket_ids:
            try:
                result = find_ticket(base, tid)
            except AmbiguousTicketMatch as e:
                print_error(f"{e}")
                raise typer.Exit(code=1) from None
            if result is None:
                typer.echo(f"Ticket not found: {tid}")
                raise typer.Exit(code=1)
            pairs.append(result)
    else:
        # No args: find ticket assigned to "hand"
        try:
            feature = resolve_current_run(base)
        except RuntimeError:
            typer.echo("No active session. Use `kd start` first.")
            raise typer.Exit(code=1) from None
        tickets_dir = branch_root(base, feature) / "tickets"
        if tickets_dir.exists():
            for t in list_tickets(tickets_dir):
                if t.assignee == "hand":
                    result = find_ticket(base, t.id)
                    if result:
                        pairs.append(result)
                    break
        if not pairs:
            typer.echo("No ticket assigned to 'hand'. Use `kd tk assign <id> hand`.")
            raise typer.Exit(code=1)

    # Render
    if output_json:
        results_json = [
            {
                "id": ticket.id,
                "status": ticket.status,
                "priority": ticket.priority,
                "type": ticket.type,
                "title": ticket.title,
                "body": ticket.body,
                "deps": [{"id": d, "status": resolve_dep_status(base, d)} for d in ticket.deps],
                "links": ticket.links,
                "created": ticket.created.isoformat(),
                "assignee": ticket.assignee,
                "path": str(ticket_path),
            }
            for ticket, ticket_path in pairs
        ]
        typer.echo(json.dumps(results_json if len(results_json) > 1 else results_json[0], indent=2))
    else:
        console = Console()
        for i, (ticket, ticket_path) in enumerate(pairs):
            if i > 0:
                console.print()  # separator between tickets
            console.print(render_ticket_panel(ticket, ticket_path, base))


def update_ticket_status(ticket_id: str, new_status: str) -> None:
    """Helper to update a ticket's status."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    old_status = ticket.status
    ticket.status = new_status
    write_ticket(ticket, ticket_path)

    # Auto-archive: closing a backlog ticket moves it to archive/backlog/tickets/
    backlog_tickets = backlog_root(base) / "tickets"
    archive_backlog_tickets = archive_root(base) / "backlog" / "tickets"
    if new_status == "closed" and ticket_path.parent.resolve() == backlog_tickets.resolve():
        ticket_path = move_ticket(ticket_path, archive_backlog_tickets)

    # Auto-restore: reopening/starting an archived backlog ticket moves it back to backlog
    if new_status in ("open", "in_progress") and ticket_path.parent.resolve() == archive_backlog_tickets.resolve():
        ticket_path = move_ticket(ticket_path, backlog_tickets)

    typer.echo(f"{ticket.id}: {old_status} → {new_status} — {ticket.title}")

    # Show newly unblocked tickets when closing
    if new_status == "closed":
        unblocked = find_newly_unblocked(ticket.id, base)
        if unblocked:
            typer.echo("")
            typer.echo(f"Unblocked {len(unblocked)} ticket(s):")
            for t in unblocked:
                typer.echo(f"  {t.id} [P{t.priority}] — {t.title}")


@ticket_app.command("start", help="Mark a ticket as in_progress.")
def ticket_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status to in_progress."""
    update_ticket_status(ticket_id, "in_progress")


@ticket_app.command("current", help="Show the in-progress ticket for this branch.")
def ticket_current(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Find and display the ticket currently marked as in_progress on this branch."""
    base = Path.cwd()

    try:
        feature = resolve_current_run(base)
    except RuntimeError:
        typer.echo("No active session. Use `kd start` first.")
        raise typer.Exit(code=1) from None

    tickets_dir = branch_root(base, feature) / "tickets"
    if not tickets_dir.exists():
        typer.echo("No in-progress ticket on this branch.")
        raise typer.Exit(code=1)

    in_progress = [t for t in list_tickets(tickets_dir) if t.status == "in_progress"]

    if not in_progress:
        typer.echo("No in-progress ticket on this branch.")
        raise typer.Exit(code=1)

    ticket = in_progress[0]
    ticket_path = tickets_dir / f"{ticket.id}.md"

    if output_json:
        result_json = {
            "id": ticket.id,
            "status": ticket.status,
            "priority": ticket.priority,
            "type": ticket.type,
            "title": ticket.title,
            "body": ticket.body,
            "deps": [{"id": d, "status": resolve_dep_status(base, d)} for d in ticket.deps],
            "links": ticket.links,
            "created": ticket.created.isoformat(),
            "assignee": ticket.assignee,
            "path": str(ticket_path),
        }
        typer.echo(json.dumps(result_json, indent=2))
    else:
        console = Console()
        console.print(f"[dim]{ticket_path.relative_to(base)}[/dim]")
        console.print(Rule(style="dim"))

        status_colors = {"open": "yellow", "in_progress": "cyan", "in_review": "magenta", "closed": "green"}
        status_color = status_colors.get(ticket.status, "white")
        console.print(
            f"[bold]{ticket.id}[/bold]  "
            f"[{status_color}]{ticket.status}[/{status_color}]  "
            f"P{ticket.priority}  "
            f"{ticket.type}"
        )
        if ticket.deps:
            dep_parts = []
            for dep_id in ticket.deps:
                dep_status = resolve_dep_status(base, dep_id)
                dep_color = status_colors.get(dep_status, "white")
                dep_parts.append(f"{dep_id} [{dep_color}]{dep_status}[/{dep_color}]")
            console.print(f"[dim]deps:[/dim] {', '.join(dep_parts)}")
        if ticket.links:
            links_str = ", ".join(ticket.links)
            console.print(f"[dim]links:[/dim] {links_str}")
        if ticket.assignee:
            console.print(f"[dim]assignee:[/dim] {ticket.assignee}")
        console.print(f"[dim]created:[/dim] {ticket.created.strftime('%Y-%m-%d')}")
        console.print()

        console.print(Markdown(f"# {ticket.title}\n\n{ticket.body}"))


@ticket_app.command("close", help="Mark a ticket as closed.")
def ticket_close(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    reason: Annotated[
        str | None, typer.Option("--reason", "-m", help="Reason for closing (appended to worklog).")
    ] = None,
) -> None:
    """Set ticket status to closed."""
    if reason:
        from kingdom.harness import append_worklog

        base = Path.cwd()
        result = find_ticket(base, ticket_id)
        if result is not None:
            _, ticket_path = result
            append_worklog(ticket_path, f"Closed: {reason}")
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
        print_error(f"{e}")
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
        typer.echo(f"{ticket.id}: now depends on {dep_ticket.id}")
    else:
        typer.echo(f"{ticket.id}: already depends on {dep_ticket.id}")


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
        print_error(f"{e}")
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
        typer.echo(f"{ticket.id}: removed dependency → {dep_id}")

    write_ticket(ticket, ticket_path)


@ticket_app.command("assign", help="Assign a ticket to an agent.")
def ticket_assign(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    agent: Annotated[str, typer.Argument(help="Agent name or 'hand' for current agent.")],
) -> None:
    """Set the assignee field on a ticket."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    ticket.assignee = agent
    write_ticket(ticket, ticket_path)
    typer.echo(f"{ticket.id}: assigned to {agent}")


@ticket_app.command("unassign", help="Clear ticket assignment.")
def ticket_unassign(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Clear the assignee field on a ticket."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    ticket.assignee = None
    write_ticket(ticket, ticket_path)
    typer.echo(f"{ticket.id}: unassigned")


@ticket_app.command("move", help="Move a ticket to another branch.")
def ticket_move(
    ticket_ids: Annotated[list[str], typer.Argument(help="Ticket ID(s) (full or partial).")],
    to_target: Annotated[str | None, typer.Option("--to", help="Target branch name or 'backlog'.")] = None,
) -> None:
    """Move ticket(s) to a different branch or backlog.

    Single ticket: `kd tk move <id> --to <branch>` or `kd tk move <id>` (to current branch).
    Multiple tickets: `kd tk move <id1> <id2> --to <branch>`.
    """
    base = Path.cwd()

    target = to_target
    # Backwards compat: if exactly 2 positional args and no --to, treat second as target
    if target is None and len(ticket_ids) == 2:
        # Check if the second arg looks like a branch name (not a ticket ID)
        second = ticket_ids[1]
        try:
            result = find_ticket(base, second)
        except AmbiguousTicketMatch:
            result = "ambiguous"
        if result is None:
            # Second arg is not a ticket, treat as target
            target = second
            ticket_ids = ticket_ids[:1]

    # Determine destination
    if target is None:
        try:
            target = resolve_current_run(base)
        except RuntimeError:
            print_error("No current branch active. Use --to <branch> or run `kd start` first.")
            raise typer.Exit(code=1) from None

    if target.lower() == "backlog":
        dest_dir = backlog_root(base) / "tickets"
        dest_label = "backlog"
    else:
        normalized = normalize_branch_name(target)
        dest_dir = branches_root(base) / normalized / "tickets"
        dest_label = f"branch '{normalized}'"

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Pass 1: validate all tickets
    validated: list[tuple[Ticket, Path]] = []
    for tid in ticket_ids:
        try:
            result = find_ticket(base, tid)
        except AmbiguousTicketMatch as e:
            print_error(f"{e}")
            raise typer.Exit(code=1) from None

        if result is None:
            typer.echo(f"Ticket not found: {tid}")
            raise typer.Exit(code=1)

        ticket, ticket_path = result
        if ticket_path.parent.resolve() == dest_dir.resolve():
            typer.echo(f"Ticket {ticket.id} is already in {dest_label}")
            continue
        validated.append((ticket, ticket_path))

    # Pass 2: move all validated tickets
    for ticket, ticket_path in validated:
        move_ticket(ticket_path, dest_dir)
        typer.echo(f"Moved {ticket.id} to {dest_label} — {ticket.title}")


@ticket_app.command("pull", help="Pull backlog tickets into the current branch.")
def ticket_pull(
    ticket_ids: Annotated[list[str], typer.Argument(help="Ticket IDs to pull from backlog.")],
) -> None:
    """Move one or more tickets from backlog to the current branch."""
    base = Path.cwd()

    try:
        resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from None

    if not ticket_ids:
        print_error("at least one ticket ID is required")
        raise typer.Exit(code=1)

    dest_dir = get_tickets_dir(base)
    backlog_tickets = backlog_root(base) / "tickets"

    # Pass 1: validate all tickets before moving any (backlog-scoped lookup)
    validated: list[tuple[Ticket, Path]] = []
    seen_ids: set[str] = set()
    for tid in ticket_ids:
        # Support both legacy kin-XXXX and new XXXX formats
        clean_id = tid[4:] if tid.startswith("kin-") else tid
        ticket_path = backlog_tickets / f"{clean_id}.md"
        if not ticket_path.exists():
            # Fall back to legacy kin- format
            ticket_path = backlog_tickets / f"kin-{clean_id}.md"
        if not ticket_path.exists():
            typer.echo(f"Ticket not found in backlog: {tid}")
            raise typer.Exit(code=1)

        ticket = read_ticket(ticket_path)

        if ticket.id in seen_ids:
            continue
        seen_ids.add(ticket.id)
        validated.append((ticket, ticket_path))

    # Pass 2: move all validated tickets
    for ticket, ticket_path in validated:
        move_ticket(ticket_path, dest_dir)
        typer.echo(f"Pulled {ticket.id} — {ticket.title}")


@ticket_app.command("ready", help="List tickets ready to work on.")
def ticket_ready(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """List open tickets with no open dependencies."""
    base = Path.cwd()

    # Collect all tickets to build status lookup
    all_tickets: list[tuple[Ticket, str]] = []  # (ticket, location)

    # branches/*/tickets/ (skip done branches)
    branches_dir = branches_root(base)
    if branches_dir.exists():
        for branch_dir in branches_dir.iterdir():
            if branch_dir.is_dir() and not is_branch_done(branch_dir):
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
            typer.echo('No ready tickets. Create one with `kd tk create "title"` or check deps with `kd tk list`.')
            return
        for ticket, _ in ready_tickets:
            typer.echo(f"{ticket.id} [P{ticket.priority}][{ticket.status}] - {ticket.title}")


@ticket_app.command("log", help="Append a worklog entry to a ticket.")
def ticket_log(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    message: Annotated[str, typer.Argument(help="Worklog message to append.")],
) -> None:
    """Append a timestamped journal entry to the ticket's Worklog section."""
    from kingdom.ticket import append_worklog_entry

    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    entry = append_worklog_entry(ticket_path, message)
    typer.echo(f"{ticket.id}: {entry}")


@ticket_app.command("edit", help="Open a ticket in $EDITOR.")
def ticket_edit(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Open a ticket file in the default editor."""
    base = Path.cwd()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        typer.echo(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    import shlex

    _, ticket_path = result
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([*shlex.split(editor), str(ticket_path)])


def main() -> None:
    app()


if __name__ == "__main__":
    main()
