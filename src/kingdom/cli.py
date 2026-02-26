"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shlex
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NamedTuple

if TYPE_CHECKING:
    from kingdom.thread import ThreadStatus

import click
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
    find_project_root,
    get_current_git_branch,
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
    collect_all_tickets,
    find_newly_unblocked,
    find_ticket,
    generate_ticket_id,
    list_tickets,
    move_ticket,
    read_ticket,
    write_ticket,
)

error_console = Console(stderr=True)

NO_COLOR = "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"


def styled_echo(message: str, *, fg: str | None = None, err: bool = False) -> None:
    """typer.secho wrapper that respects NO_COLOR and TERM=dumb."""
    typer.secho(message, fg=None if NO_COLOR else fg, err=err)


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

VERBOSE: bool = False


@app.callback()
def app_callback(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Print debug output.")] = False,
) -> None:
    global VERBOSE
    VERBOSE = verbose


def verbose_echo(message: str) -> None:
    """Print a debug message to stderr when --verbose is set."""
    if VERBOSE:
        error_console.print(f"[dim]{message}[/dim]")


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


@app.command(help="Initialize .kd/ directory structure.")
def init(
    no_git: Annotated[bool, typer.Option("--no-git", help="Skip git repository check.")] = False,
    no_gitignore: Annotated[bool, typer.Option("--no-gitignore", help="Skip .gitignore creation.")] = False,
) -> None:
    """Initialize the .kd/ directory structure for Kingdom.

    Idempotent: creates missing pieces, skips existing.
    """
    base = Path.cwd()  # init anchors to cwd — user chooses where to create .kd/

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

    install_skill()

    typer.echo(f"Initialized {paths['state_root']}")


@app.command("setup-skill", help="Symlink the kingdom agent skill into ~/.claude/skills/.")
def setup_skill() -> None:
    """Create a symlink from ~/.claude/skills/kingdom to skills/kingdom/ in this repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    base = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else Path.cwd()
    source = base / "skills" / "kingdom"
    if not source.exists():
        print_error(f"Skill directory not found: {source}")
        raise typer.Exit(code=1)

    target = Path.home() / ".claude" / "skills" / "kingdom"
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_symlink():
        existing = target.resolve()
        if existing == source.resolve():
            typer.echo(f"Already linked: {target} -> {source}")
            return
        typer.echo(f"Updating symlink: {target} (was -> {existing})")
        target.unlink()
    elif target.exists():
        print_error(f"{target} exists and is not a symlink. Remove it manually to proceed.")
        raise typer.Exit(code=1)

    target.symlink_to(source)
    typer.echo(f"Linked {target} -> {source}")


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
            print_error("Not a git repository. Run `kd init --no-git` first.")
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
            print_error(f"'{thread_id}' matches multiple threads:")
            for m in exc.matches:
                topic = topic_for_thread(base, feature, m.id)
                label = f"  {m.id}  {m.created_at.strftime('%Y-%m-%d %H:%M')}"
                if topic:
                    label += f"  {topic}"
                error_console.print(label)
            error_console.print(f"\nBe more specific, e.g.: kd council {command} {exc.matches[0].id}")
            raise typer.Exit(code=1) from None
        except ThreadNotFoundError as exc:
            print_error(f"Thread not found: {thread_id}")
            if exc.available:
                error_console.print("\nAvailable council threads:")
                for t in exc.available[-5:]:
                    topic = topic_for_thread(base, feature, t.id)
                    label = f"  {t.id}  {t.created_at.strftime('%Y-%m-%d %H:%M')}"
                    if topic:
                        label += f"  {topic}"
                    error_console.print(label)
                if len(exc.available) > 5:
                    error_console.print(f"  ... and {len(exc.available) - 5} more (use `kd council list`)")
            else:
                print_error("No council threads exist. Use `kd council ask` to start one.")
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
    print_error("No council threads. Use `kd council ask` to start one.")
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

    base = require_project_root()
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

    verbose_echo(f"base: {base}")
    verbose_echo(f"branch: {feature}")
    verbose_echo(f"members: {', '.join(m.name for m in c.members)}")
    verbose_echo(f"timeout: {timeout}s")
    verbose_echo(f"logs: {logs_dir}")

    # Parse @mentions from prompt (kin-09c9), ignoring content inside code blocks
    available_names = {m.name for m in c.members}
    if not to:
        prompt_without_code = re.sub(r"```[\s\S]*?```", "", prompt)
        mentions = re.findall(r"(?<!\w)@(\w+)", prompt_without_code)
        if mentions:
            if "all" in mentions:
                # @all = query everyone, strip @all from prompt
                prompt = re.sub(r"(?<!\w)@all\b\s*", "", prompt).strip()
            else:
                unknown = [m for m in mentions if m not in available_names]
                if unknown:
                    print_error(f"Unknown @mention(s): {', '.join(unknown)}")
                    print_error(f"Available: {', '.join(sorted(available_names))}")
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
            print_error(f"Unknown member: {to}")
            print_error(f"Available: {', '.join(sorted(available_names))}")
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

    tdir = thread_dir(base, feature, thread_id)
    verbose_echo(f"thread: {thread_id} ({'new' if start_new else 'continuing'})")
    verbose_echo(f"thread dir: {tdir}")

    # Write king's message to thread
    target = to or "all"
    add_message(base, feature, thread_id, from_="king", to=target, body=prompt)

    # --json mode: batch query (always sync, no streaming)
    if json_output:
        if to and member:
            response = member.query(prompt, timeout)
            responses = {to: response}
            add_message(
                base,
                feature,
                thread_id,
                from_=to,
                to="king",
                body=response.thread_body(),
                status=response.thread_status(),
            )
        else:
            responses = query_with_progress(c, prompt, json_output, console)
            for name, resp in responses.items():
                add_message(
                    base,
                    feature,
                    thread_id,
                    from_=name,
                    to="king",
                    body=resp.thread_body(),
                    status=resp.thread_status(),
                )

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
        add_message(
            base, feature, thread_id, from_=to, to="king", body=response.thread_body(), status=response.thread_status()
        )
        render_response(response, console)
    else:

        def on_response(name, response):
            render_response(response, console)

        c.query_to_thread(prompt, base, feature, thread_id, callback=on_response)

    c.save_sessions(base, feature)


def detect_base_branch() -> str:
    """Detect the default base branch (main or master)."""
    for candidate in ("origin/main", "origin/master", "main", "master"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return candidate
    return "master"


@council_app.command("review", help="Ask the council to review code changes.")
def council_review(
    base_branch: Annotated[str | None, typer.Option("--base", "-b", help="Base branch to diff against.")] = None,
    to: Annotated[str | None, typer.Option("--to", help="Send to a specific member only.")] = None,
    async_mode: Annotated[
        bool, typer.Option("--async", help="Dispatch in background, then watch for responses.")
    ] = False,
    no_watch: Annotated[bool, typer.Option("--no-watch", help="With --async, dispatch only without watching.")] = False,
    writable: Annotated[
        bool, typer.Option("--writable", "-w", help="Grant council members full write permissions.")
    ] = False,
) -> None:
    """Generate a changed-files summary and ask the council to review it."""
    base = require_project_root()
    resolve_current_run(base)  # Validate active session

    if base_branch is None:
        base_branch = detect_base_branch()

    # Get changed file stats
    stat_result = subprocess.run(
        ["git", "diff", "--stat", f"{base_branch}...HEAD"],
        capture_output=True,
        text=True,
    )
    if stat_result.returncode != 0:
        print_error(f"Failed to generate diff against {base_branch}: {stat_result.stderr.strip()}")
        raise typer.Exit(code=1)

    stat_output = stat_result.stdout.strip()
    if not stat_output:
        typer.echo(f"No changes between {base_branch} and HEAD.")
        raise typer.Exit(code=0)

    # Get commit log for context
    log_result = subprocess.run(
        ["git", "log", "--oneline", f"{base_branch}..HEAD"],
        capture_output=True,
        text=True,
    )
    commits = log_result.stdout.strip()

    # Build the review prompt — agents read files themselves
    prompt_parts = [
        f"Review the code changes on this branch vs {base_branch}.",
        "Read the changed files listed below. Focus on: correctness, edge cases, readability, and potential bugs.",
        "Be specific — reference file names and line numbers.",
    ]
    if commits:
        prompt_parts.append(f"\n## Commits\n\n```\n{commits}\n```")
    prompt_parts.append(f"\n## Changed files\n\n```\n{stat_output}\n```")
    review_prompt = "\n".join(prompt_parts)

    # Delegate to council_ask with --new-thread
    council_ask(
        prompt=review_prompt,
        to=to,
        new_thread=True,
        json_output=False,
        async_mode=async_mode,
        no_watch=no_watch,
        writable=writable,
    )


@council_app.command("reset", help="Clear council sessions.")
def council_reset(
    member_name: Annotated[str | None, typer.Option("--member", help="Reset only this member's session.")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt.")] = False,
) -> None:
    """Clear council member sessions. Use --member to reset a single member."""
    base = require_project_root()
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
            print_error(f"Unknown member: {member_name}")
            error_console.print(f"Available: {available}")
            raise typer.Exit(code=1)
        if not force:
            typer.confirm(f"Clear session for {member_name}?", abort=True)
        m.reset_session()
        c.save_sessions(base, feature)
        typer.echo(f"Session cleared for {member_name}")
    else:
        if not force:
            member_names = ", ".join(sorted(mem.name for mem in c.members))
            typer.confirm(f"Clear all council sessions ({member_names})?", abort=True)
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
        if msg.status and msg.status != "complete":
            subtitle += f" · {msg.status}"
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
                print_error('No council history found. Start a conversation with `kd council ask "prompt"`.')
                raise typer.Exit(code=1)
            runs = [d for d in council_logs_dir.iterdir() if d.is_dir() and d.name.startswith("run-")]
            if not runs:
                print_error('No council history found. Start a conversation with `kd council ask "prompt"`.')
                raise typer.Exit(code=1)
            run_dir = max(runs, key=lambda d: d.stat().st_mtime)
        else:
            print_error(f"Legacy run not found: {thread_id}")
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

    base = require_project_root()
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
        print_error(f'Thread {thread_id}: no messages. Send one with `kd council ask "prompt"`.')
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

    base = require_project_root()
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

    base = require_project_root()
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

    from kingdom.agent import resolve_all_agents
    from kingdom.config import load_config
    from kingdom.council.base import AgentResponse
    from kingdom.thread import get_thread, list_messages, thread_dir
    from kingdom.tui.poll import tail_stream_file

    base = require_project_root()
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

    member_backends: dict[str, str] = {}
    try:
        cfg = load_config(base)
        agent_configs = resolve_all_agents(cfg.agents)
        for name in expected_members:
            ac = agent_configs.get(name)
            if ac:
                member_backends[name] = ac.backend
    except (KeyError, OSError, TypeError, ValueError) as exc:
        console.print(
            f"[yellow]Warning:[/yellow] stream preview disabled ({exc}); finalized messages will still appear."
        )

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
        """Read new lines from .stream-{member}.jsonl files via tail_stream_file."""
        for name in expected_members - responded_members:
            stream_file = tdir / f".stream-{name}.jsonl"
            if not stream_file.exists():
                if name in streaming_members:
                    streaming_members.discard(name)
                    stream_positions.pop(name, None)
                continue

            streaming_members.add(name)
            backend = member_backends.get(name, "claude_code")
            pos = stream_positions.get(name, 0)

            # Detect file recreation (retry): file smaller than our offset
            try:
                file_size = stream_file.stat().st_size
                if file_size < pos:
                    pos = 0
                    accumulated_text.pop(name, None)
            except OSError:
                continue

            if file_size <= pos:
                continue

            text, _thinking, _tools = tail_stream_file(stream_file, pos, backend)
            stream_positions[name] = file_size
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

    base = require_project_root()
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
        print_error('No king message found in thread. Send one first with `kd council ask "prompt"`.')
        raise typer.Exit(code=1)

    prompt = last_king_msg.body

    # Derive expected members from the last ask's target (not thread-level members)
    if last_king_msg.to == "all":
        expected = all_members
    else:
        # Single or comma-separated targets
        expected = {t.strip() for t in last_king_msg.to.split(",") if t.strip() != "king"} & all_members

    # Find members that responded successfully after the last ask.
    # Check msg.status first (new metadata), fall back to body prefix for legacy messages.
    ok_members: set[str] = set()
    for msg in messages:
        if msg.sequence > last_king_msg.sequence and msg.from_ in expected:
            if msg.status:
                if msg.status == "complete":
                    ok_members.add(msg.from_)
            elif not is_error_response(msg.body):
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
        print_error(f"Failed members ({', '.join(sorted(failed))}) not found in council config.")
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
    color: Annotated[
        str,
        typer.Option(
            "--color",
            help="Color mode: auto, truecolor, ansi, none.",
            click_type=click.Choice(["auto", "truecolor", "ansi", "none"]),
        ),
    ] = "auto",
) -> None:
    """Open the council chat TUI.

    Opens an existing thread, creates a new one, or lists recent threads.
    """
    from kingdom.config import load_config
    from kingdom.thread import create_thread, list_threads

    base = require_project_root()
    feature = resolve_current_run(base)
    cfg = load_config(base)

    if new:
        tid = f"council-{secrets.token_hex(2)}"
        member_names = cfg.council.members or list(cfg.agents)
        create_thread(base, feature, tid, ["king", *member_names], "council")
        set_current_thread(base, feature, tid)
    elif thread_id:
        tid = resolve_council_thread_id(base, feature, thread_id, command="chat")
        set_current_thread(base, feature, tid)
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
                for t in reversed(threads[-5:]):
                    created = t.created_at.strftime("%Y-%m-%d %H:%M")
                    members = ", ".join(m for m in t.members if m != "king")
                    typer.echo(f"  {t.id}  {created}  [{members}]")
                typer.echo()
                typer.echo("Usage: kd chat <thread-id>  or  kd chat --new")
            else:
                typer.echo("No threads found. Create one with: kd chat --new")
            raise typer.Exit(code=0)

    from kingdom.tui.app import ChatApp
    from kingdom.tui.terminal import in_tmux_control_mode

    # Resolve color mode
    explicit_color = color != "auto"
    if color == "auto":
        use_ansi = in_tmux_control_mode()
        if use_ansi:
            typer.echo("Detected tmux control mode (-CC) — using ANSI colors for compatibility.")
    elif color == "ansi":
        use_ansi = True
    elif color == "none":
        os.environ["NO_COLOR"] = "1"
        use_ansi = True
    else:  # truecolor
        use_ansi = False

    app_instance = ChatApp(
        base=base, branch=feature, thread_id=tid, debug_streams=debug, writable=writable, ansi_color=use_ansi
    )

    try:
        app_instance.run()
    except AttributeError as exc:
        if "_color" not in str(exc) or explicit_color:
            raise
        # Crash fallback: retry once with ANSI color mode (only when --color was auto)
        typer.echo()
        typer.echo("TUI crashed with a color rendering error. Retrying with ANSI color mode...")
        typer.echo("Hint: run with --color ansi to skip auto-detection, or --color none to disable colors.")
        app_instance = ChatApp(
            base=base, branch=feature, thread_id=tid, debug_streams=debug, writable=writable, ansi_color=True
        )
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
    base = require_project_root()
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
    base = require_project_root()
    feature = resolve_current_run(base)
    design_path, _ = get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        print_error("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    console = Console()
    console.print(Markdown(design_path.read_text(encoding="utf-8")))


@design_app.command("approve", help="Mark the design as approved.")
def design_approve() -> None:
    """Set design_approved=true in state.json."""
    base = require_project_root()
    feature = resolve_current_run(base)
    design_path, state_path = get_design_paths(base, feature)

    if not design_path.exists() or not design_path.read_text(encoding="utf-8").strip():
        print_error("No design document found. Run `kd design` to create one.")
        raise typer.Exit(code=1)

    state = read_json(state_path) if state_path.exists() else {}
    state["design_approved"] = True
    write_json(state_path, state)
    typer.echo("Design approved")


@app.command(help="Draft or iterate the current breakdown.")
def breakdown() -> None:
    base = require_project_root()
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

    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        capture_output=True,
        text=True,
    )
    branch_exists = result.returncode == 0

    if branch_exists:
        typer.echo(f"Creating worktree from existing branch {branch_name}...")
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            capture_output=True,
            text=True,
        )
    else:
        typer.echo(f"Creating worktree with new branch {branch_name}...")
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        raise RuntimeError(f"Error creating worktree: {result.stderr.strip()}")

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

    try:
        feature = resolve_current_run(base)
        _, state_path = get_design_paths(base, feature)
        state = read_json(state_path) if state_path.exists() else {}
        worktrees = state.get("worktrees", {})
        worktrees[full_ticket_id] = str(worktree_path)
        state["worktrees"] = worktrees
        write_json(state_path, state)
    except RuntimeError as exc:
        typer.echo(f"Warning: could not record worktree in state.json: {exc}")

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
    except RuntimeError as exc:
        typer.echo(f"Warning: could not update state.json worktree map: {exc}")


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
    base = base or require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    try:
        result = find_ticket(base, ticket_id, branch=feature)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
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


def launch_work_tmux(
    base: Path,
    feature: str,
    ticket_id: str,
    agent: str,
    worktree_path: Path,
    thread_id: str,
    session_name: str,
) -> int:
    """Launch ``kd work`` in a new tmux window.

    Errors if tmux is not running. Returns the PID of the tmux
    new-window shell (the agent process runs inside it).
    """
    # Check tmux is running
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print_error("tmux is not running. Start tmux first or omit --tmux.")
            raise typer.Exit(code=1)
    except FileNotFoundError:
        print_error("tmux is not installed.")
        raise typer.Exit(code=1) from None

    work_cmd = " ".join(
        [
            shlex.quote(sys.executable),
            "-m",
            "kingdom.cli",
            "work",
            shlex.quote(ticket_id),
            "--agent",
            shlex.quote(agent),
            "--worktree",
            shlex.quote(str(worktree_path)),
            "--thread",
            shlex.quote(thread_id),
            "--session",
            shlex.quote(session_name),
            "--base",
            shlex.quote(str(base)),
        ]
    )

    window_name = f"peasant-{ticket_id}"
    tmux_cmd = [
        "tmux",
        "new-window",
        "-n",
        window_name,
        "-P",  # print window info
        work_cmd,
    ]

    proc = subprocess.run(tmux_cmd, capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        print_error(f"failed to create tmux window: {proc.stderr.strip()}")
        raise typer.Exit(code=1)

    # Get the PID of the shell running in the new window
    # tmux new-window -P prints something like "main:2.0"
    # We'll use tmux list-panes to find the PID
    pane_target = proc.stdout.strip()
    try:
        pid_result = subprocess.run(
            ["tmux", "list-panes", "-t", pane_target, "-F", "#{pane_pid}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pid = int(pid_result.stdout.strip().splitlines()[0])
    except (ValueError, IndexError, subprocess.TimeoutExpired):
        pid = 0  # Can't determine PID — still functional

    return pid


@peasant_app.command("start", help="Launch a peasant agent on a ticket.")
def peasant_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID to work on.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent to use (default: from config).")] = None,
    hand: Annotated[bool, typer.Option("--hand", help="Run in current directory (serial mode).")] = False,
    tmux: Annotated[bool, typer.Option("--tmux", help="Open agent in a new tmux window.")] = False,
) -> None:
    """Create worktree, session, thread, and launch agent harness in background."""
    from kingdom.config import load_config
    from kingdom.session import update_agent_state
    from kingdom.thread import create_thread

    ctx = resolve_peasant_context(ticket_id, auto_pull=True)
    base, ticket, full_ticket_id, feature = ctx.base, ctx.ticket, ctx.full_ticket_id, ctx.feature

    # Block starting work on tickets that are in_review or closed
    if ticket.status in ("in_review", "closed"):
        print_error(f"Cannot start work on {full_ticket_id}: ticket is {ticket.status}")
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
            print_error(f"Peasant already running on {full_ticket_id} (pid {existing.pid})")
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
                    print_error(
                        f"peasant {active.name} (pid {active.pid}) is already working "
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
            print_error(str(exc))
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

    # 4. Launch harness
    if tmux:
        pid = launch_work_tmux(base, feature, full_ticket_id, agent, worktree_path, thread_id, session_name)
    else:
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
        hand_mode=hand,
    )

    peasant_logs_dir = logs_root(base, feature) / session_name
    mode = "tmux" if tmux else "background"
    typer.echo(f"Started {session_name} (pid {pid}, {mode})")
    typer.echo(f"  Agent: {agent}")
    typer.echo(f"  Ticket: {full_ticket_id}")
    typer.echo(f"  Worktree: {worktree_path}")
    typer.echo(f"  Thread: {thread_id}")
    typer.echo(f"  Logs: {peasant_logs_dir}")
    verbose_echo(f"ticket path: {ctx.ticket_path}")
    verbose_echo(f"thread dir: {tdir}")
    verbose_echo(f"hand mode: {hand}")


TERMINAL_STATUSES = {"done", "failed", "stopped"}


@peasant_app.command("status", help="Show active peasants.")
def peasant_status(
    show_all: Annotated[bool, typer.Option("--all", "-a", help="Include completed/stopped peasants.")] = False,
) -> None:
    """Show table of active peasants: ticket, agent, status, elapsed, last activity."""

    from kingdom.session import list_active_agents

    base = require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    console = Console()
    active = list_active_agents(base, feature)

    # Filter to peasant sessions only
    peasants = [a for a in active if a.name.startswith("peasant-")]

    # By default, hide terminal sessions
    hidden: list = []
    if not show_all:
        all_peasants = peasants
        peasants = [p for p in peasants if p.status not in TERMINAL_STATUSES]
        hidden = [p for p in all_peasants if p.status in TERMINAL_STATUSES]

    if not peasants:
        if hidden:
            from collections import Counter

            counts = Counter(p.status for p in hidden)
            parts = [f"{n} {s}" for s, n in sorted(counts.items())]
            summary = ", ".join(parts)
            typer.echo(f"No active peasants ({summary} — use --all to show).")
        else:
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
            "awaiting_council": "magenta",
            "needs_king_review": "cyan",
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
    if hidden:
        from collections import Counter

        counts = Counter(p.status for p in hidden)
        parts = [f"{n} {s}" for s, n in sorted(counts.items())]
        summary = ", ".join(parts)
        console.print(f"[dim]{summary} — use --all to show[/dim]")


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
        print_error(f"No logs found for {ctx.full_ticket_id}. Has the peasant been started?")
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


@peasant_app.command("watch", help="Watch peasant progress in real time.")
def peasant_watch(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
) -> None:
    """Tail the ticket worklog and show progress as the peasant works.

    Exits on Ctrl+C or when the peasant finishes (terminal status).
    """
    import time as time_mod

    from kingdom.session import get_agent_state

    ctx = resolve_peasant_context(ticket_id)
    session_name = f"peasant-{ctx.full_ticket_id}"

    console = Console()
    console.print(f"[bold]Watching {session_name}[/bold]  (Ctrl+C to stop)\n")

    # Track what we've already shown
    shown_lines: int = 0

    def get_worklog_lines() -> list[str]:
        """Read current worklog lines from the ticket file."""
        from kingdom.harness import extract_worklog

        worklog = extract_worklog(ctx.ticket_path)
        if not worklog.strip():
            return []
        return worklog.strip().splitlines()

    try:
        while True:
            # Print new worklog lines
            lines = get_worklog_lines()
            if len(lines) > shown_lines:
                for line in lines[shown_lines:]:
                    console.print(line)
                shown_lines = len(lines)

            # Check if peasant is still running
            state = get_agent_state(ctx.base, ctx.feature, session_name)
            if state.status in TERMINAL_STATUSES:
                console.print(f"\n[bold]Peasant finished: {state.status}[/bold]")
                break

            time_mod.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


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
        print_error(f"Peasant {full_ticket_id} is not running (status: {state.status})")
        raise typer.Exit(code=1)

    if not state.pid:
        print_error(f"No PID found for peasant {full_ticket_id}")
        raise typer.Exit(code=1)

    # Kill the entire process group (harness + backend + children).
    # The harness is launched with start_new_session=True, so its PID
    # is the process group leader.
    pgid = state.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
        typer.echo(f"{full_ticket_id}: sent SIGTERM to process group (pgid {pgid})")
    except OSError as e:
        typer.echo(f"Process group {pgid} not found: {e}")

    # Wait for processes to exit, then SIGKILL stragglers
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # check if any process in group is alive
        except OSError:
            break  # all dead
        time.sleep(0.2)
    else:
        # Still alive after timeout — force kill
        try:
            os.killpg(pgid, signal.SIGKILL)
            typer.echo(f"{full_ticket_id}: sent SIGKILL to process group (pgid {pgid})")
        except OSError:
            pass  # already dead

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
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt.")] = False,
) -> None:
    """Remove the git worktree for a ticket."""
    ctx = resolve_peasant_context(ticket_id)

    if not force:
        typer.confirm(f"Remove worktree for {ctx.full_ticket_id}?", abort=True)

    try:
        remove_worktree(ctx.base, ctx.full_ticket_id)
        typer.echo(f"{ctx.full_ticket_id}: worktree removed")
    except FileNotFoundError:
        print_error(f"No worktree found for {ctx.full_ticket_id}")
        raise typer.Exit(code=1) from None
    except RuntimeError as exc:
        print_error(str(exc))
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
            print_error(
                f"Peasant is running on {full_ticket_id} (pid {state.pid}). Stop it first with `kd peasant stop`."
            )
            raise typer.Exit(code=1)
        except OSError:
            pass  # Process is dead, safe to sync

    # Find worktree
    worktree_path = worktree_path_for(base, full_ticket_id)
    if not worktree_path.exists():
        print_error(f"No worktree found for {full_ticket_id}. Has the peasant been started?")
        raise typer.Exit(code=1)

    # Merge parent branch into worktree
    parent_branch = feature
    typer.echo(f"[1/2] Merging {parent_branch} into worktree for {full_ticket_id}...")
    merge_result = subprocess.run(
        ["git", "merge", parent_branch, "--no-edit"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )

    if merge_result.returncode != 0:
        print_error("Merge failed.")
        if merge_result.stdout.strip():
            error_console.print(merge_result.stdout.strip())
        if merge_result.stderr.strip():
            error_console.print(merge_result.stderr.strip())
        subprocess.run(["git", "merge", "--abort"], capture_output=True, cwd=worktree_path)
        error_console.print(f"\nMerge aborted. To resolve manually:\n  cd {worktree_path}\n  git merge {parent_branch}")
        raise typer.Exit(code=1)

    merge_out = merge_result.stdout.strip()
    if "Already up to date" in merge_out:
        typer.echo("Already up to date.")
    elif merge_out:
        typer.echo(merge_out)

    # Run init-worktree.sh to refresh dependencies
    init_script = state_root(base) / "init-worktree.sh"
    if init_script.exists() and os.access(init_script, os.X_OK):
        typer.echo("[2/2] Running init-worktree.sh...")
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
        typer.echo("[2/2] init-worktree.sh exists but is not executable, skipping.")
    else:
        typer.echo("[2/2] No init-worktree.sh found, skipping dependency refresh.")

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
        print_error(f"No work thread found for {full_ticket_id}. Has the peasant been started?")
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
        print_error(f"No work thread found for {full_ticket_id}. Has the peasant been started?")
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
    no_resume: Annotated[bool, typer.Option("--no-resume", help="Don't auto-resume peasant on reject.")] = False,
) -> None:
    """Show diff, worklog, and council feedback. Accept or reject the work."""
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
        # Gate: ticket must be in_review
        if ticket.status != "in_review":
            print_error(f"Cannot accept: ticket is '{ticket.status}', expected 'in_review'.")
            raise typer.Exit(code=1)

        # Gate: session must be needs_king_review
        state = get_agent_state(base, feature, session_name)
        if state.status != "needs_king_review":
            print_error(f"Cannot accept: session is '{state.status}', expected 'needs_king_review'.")
            raise typer.Exit(code=1)

        # Gate: must be on the feature branch
        current_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(base),
        ).stdout.strip()
        if normalize_branch_name(current_branch) != normalize_branch_name(feature):
            print_error(
                f"Cannot accept: expected to be on '{feature}' but HEAD is on '{current_branch}'. "
                "Switch branches and retry."
            )
            raise typer.Exit(code=1)

        if state.hand_mode:
            # Hand mode: changes are already on the feature branch, skip merge
            typer.echo(f"Hand mode — changes already on {feature}, skipping merge")
        else:
            # Worktree mode: merge ticket branch into feature branch
            worktree_path = worktree_path_for(base, full_ticket_id)
            merge_result = subprocess.run(
                ["git", "merge", branch_name, "--no-edit"],
                capture_output=True,
                text=True,
                cwd=str(base),
            )
            if merge_result.returncode != 0:
                # Integration failed — keep in_review, show recovery steps
                merge_err = merge_result.stdout.strip()
                if merge_result.stderr.strip():
                    merge_err += "\n" + merge_result.stderr.strip()
                print_error("Integration failed — ticket remains in_review.")
                error_console.print(f"\n{merge_err}\n")
                error_console.print("Recovery steps:")
                error_console.print(f"  1. cd {worktree_path}")
                error_console.print(f"  2. git merge {feature} (resolve conflicts)")
                error_console.print(f"  3. kd peasant review {full_ticket_id} --accept (retry)")
                raise typer.Exit(code=1)

            typer.echo(f"Integrated {branch_name} into {feature}")

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
        # Gate: ticket must be in_review
        if ticket.status != "in_review":
            print_error(f"Cannot reject: ticket is '{ticket.status}', expected 'in_review'.")
            raise typer.Exit(code=1)

        # Gate: session must be needs_king_review
        state = get_agent_state(base, feature, session_name)
        if state.status != "needs_king_review":
            print_error(f"Cannot reject: session is '{state.status}', expected 'needs_king_review'.")
            raise typer.Exit(code=1)

        # Gate: old process must be dead before relaunching
        if not no_resume and state.pid:
            try:
                os.kill(state.pid, 0)
                print_error(f"Peasant process (pid {state.pid}) is still alive. Stop it first or use --no-resume.")
                raise typer.Exit(code=1)
            except OSError:
                pass  # Process is dead, safe to relaunch

        try:
            add_message(base, feature, thread_id, from_="king", to=session_name, body=reject)
        except FileNotFoundError:
            print_error(
                f"No work thread found for {full_ticket_id}. Start one with `kd peasant start {full_ticket_id}`."
            )
            raise typer.Exit(code=1) from None

        # Transition ticket back to in_progress
        ticket.status = "in_progress"
        write_ticket(ticket, ticket_path)

        if no_resume:
            update_agent_state(
                base,
                feature,
                session_name,
                status="working",
                pid=None,
                review_bounce_count=0,
                last_activity=datetime.now(UTC).isoformat(),
            )
            typer.echo(f"{full_ticket_id}: rejected — feedback sent, ticket back to in_progress")
            return

        # Auto-resume: relaunch the peasant
        agent_backend = state.agent_backend or "claude"

        if state.hand_mode:
            # Hand mode: relaunch in-place using base repo
            from kingdom.session import list_active_agents

            for active in list_active_agents(base, feature):
                if active.name == session_name:
                    continue
                if active.status == "working" and active.pid and active.name.startswith("peasant-"):
                    try:
                        os.kill(active.pid, 0)
                        print_error(
                            f"Peasant {active.name} (pid {active.pid}) is already working on this checkout. "
                            "Stop it first or use --no-resume."
                        )
                        raise typer.Exit(code=1)
                    except OSError:
                        pass
            worktree_path = base
        else:
            # Worktree mode: use the ticket worktree
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
            review_bounce_count=0,
            last_activity=now,
        )
        typer.echo(f"{full_ticket_id}: rejected — feedback sent, peasant relaunched (pid {pid})")
        return

    # --- Show review info ---

    # 1. Show diff
    review_state = get_agent_state(base, feature, session_name)
    if review_state.hand_mode:
        if review_state.start_sha:
            diff_spec = f"{review_state.start_sha}..HEAD"
        else:
            diff_spec = "HEAD"
    else:
        diff_spec = f"HEAD...{branch_name}"
    diff_result = subprocess.run(
        ["git", "diff", diff_spec, "--stat"],
        capture_output=True,
        text=True,
        cwd=str(base),
    )
    diff_output = diff_result.stdout.strip()
    diff_err = diff_result.stderr.strip()
    has_diff = False
    if diff_result.returncode != 0 and diff_err:
        console.print(Markdown(f"## diff error: {diff_spec}\n\n```\n{diff_err}\n```"))
    elif diff_output:
        has_diff = True
        console.print(Markdown(f"## diff: {diff_spec}\n\n```\n{diff_output}\n```"))
    else:
        styled_echo("⚠ No code diff — the peasant may not have made any changes.", fg=typer.colors.YELLOW)

    # 4. Show worklog
    worklog = extract_worklog(ticket_path)
    if worklog:
        console.print(Markdown(f"## Worklog\n\n{worklog}"))
    else:
        typer.echo("(no worklog entries)")

    # 5. Show council feedback (messages from council members in the work thread)
    try:
        from kingdom.thread import list_messages

        messages = list_messages(base, feature, thread_id)
        council_msgs = [m for m in messages if m.from_ not in ("king", session_name)]
        if council_msgs:
            feedback_parts = []
            for msg in council_msgs:
                feedback_parts.append(f"### {msg.from_}\n\n{msg.body}")
            console.print(Markdown("## Council Feedback\n\n" + "\n\n---\n\n".join(feedback_parts)))
    except FileNotFoundError:
        pass  # No work thread yet — skip council feedback

    # 6. Show session status
    state = get_agent_state(base, feature, session_name)
    typer.echo(f"\nTicket status: {ticket.status}")
    typer.echo(f"Peasant status: {state.status}")
    if state.review_bounce_count:
        typer.echo(f"Review bounces: {state.review_bounce_count}")

    # Warn if no code diff
    if not has_diff and state.status == "needs_king_review":
        styled_echo("\nWarning: no code diff detected — peasant may not have made meaningful changes.", fg="yellow")

    # Prompt for action
    can_accept = ticket.status == "in_review" and state.status == "needs_king_review"
    if can_accept:
        typer.echo("\nUse --accept to close the ticket or --reject 'feedback' to send feedback.")
    else:
        typer.echo("\nUse --reject 'feedback' to send feedback.")


@app.command("work", help="Run autonomous agent loop on a ticket.")
def work(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Agent name (default: from config).")] = None,
    worktree: Annotated[str | None, typer.Option("--worktree", help="Worktree path (internal).")] = None,
    thread: Annotated[str | None, typer.Option("--thread", help="Thread ID (internal).")] = None,
    session: Annotated[str | None, typer.Option("--session", help="Session name (internal).")] = None,
    base_dir: Annotated[str | None, typer.Option("--base", help="Project root.")] = None,
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

    base = Path(base_dir).resolve() if base_dir else require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
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
        print_error("MVP uses `kd peasant start <ticket>` for single-ticket execution.")
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
    base = require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
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
    """Print the effective config with source annotations (config file vs defaults)."""
    import dataclasses

    from kingdom.config import load_config, load_raw_config

    base = require_project_root()
    try:
        cfg = load_config(base)
    except ValueError as e:
        styled_echo(f"Error: invalid config — {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    raw = load_raw_config(base)

    verbose_echo(f"base: {base}")
    config_path = base / ".kd" / "config.json"
    verbose_echo(f"config path: {config_path} ({'exists' if config_path.exists() else 'not found'})")

    def flatten(obj, prefix=""):
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                items.extend(flatten(v, f"{prefix}{k}."))
        elif isinstance(obj, list):
            items.append((prefix.rstrip("."), ", ".join(str(x) for x in obj)))
        else:
            items.append((prefix.rstrip("."), obj))
        return items

    def is_in_raw(dotted_key: str) -> bool:
        """Check if a dotted key was explicitly set in the config file.

        Tries all possible split points to handle keys containing dots
        (e.g. agent names like 'gpt.4o').
        """

        def walk(key: str, node: dict) -> bool:
            if not isinstance(node, dict):
                return False
            # Try each possible split: first segment as dict key, rest recursed
            for i in range(1, len(key) + 1):
                prefix = key[:i]
                rest = key[i + 1 :]  # skip the dot
                if prefix in node:
                    if not rest:
                        return True
                    if walk(rest, node[prefix]):
                        return True
            return False

        return walk(dotted_key, raw)

    effective = dataclasses.asdict(cfg)
    entries = flatten(effective)

    # Filter out empty values (empty strings, empty lists, empty dicts)
    entries = [(k, v) for k, v in entries if v not in ("", [], {}, None)]

    if not entries:
        typer.echo("(all defaults, no config file)")
        return

    key_width = max(len(k) for k, _ in entries)
    for key, value in entries:
        source = "config" if is_in_raw(key) else "default"
        color = typer.colors.CYAN if source == "config" else None
        styled_echo(f"  {key:<{key_width}}  {value!s}  ({source})", fg=color)


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

    base = require_project_root()
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

    base = require_project_root()
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
    parent: Annotated[str | None, typer.Option("--parent", help="Parent ticket ID.")] = None,
    tags: Annotated[str | None, typer.Option("--tags", help="Comma-separated tags.")] = None,
) -> None:
    """Create a new ticket in the current branch or backlog."""
    from datetime import datetime

    base = require_project_root()

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
                print_error(f"Dependency ticket not found: {dep_id}")
                raise typer.Exit(code=1)
            resolved_deps.append(dep_result[0].id)

    # Resolve parent
    resolved_parent = None
    if parent:
        try:
            parent_result = find_ticket(base, parent)
        except AmbiguousTicketMatch as e:
            print_error(f"{e}")
            raise typer.Exit(code=1) from None
        if parent_result is None:
            print_error(f"Parent ticket not found: {parent}")
            raise typer.Exit(code=1)
        resolved_parent = parent_result[0].id

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

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
        parent=resolved_parent,
        tags=tag_list,
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


def filter_tickets_by_status(
    tickets: list[Ticket],
    status: str | None,
    include_closed: bool,
) -> list[Ticket]:
    if status is not None:
        return [ticket for ticket in tickets if ticket.status == status]
    if not include_closed:
        return [ticket for ticket in tickets if ticket.status != "closed"]
    return tickets


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
    priority: Annotated[
        int | None,
        typer.Option("--priority", "-p", help="Filter by priority (1-3)."),
    ] = None,
    backlog: Annotated[bool, typer.Option("--backlog", help="List open tickets in backlog only.")] = False,
    assignee: Annotated[str | None, typer.Option("--assignee", "-A", help="Filter by assignee.")] = None,
    tag: Annotated[str | None, typer.Option("--tag", "-T", help="Filter by tag.")] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """List tickets in the current branch or all locations."""
    if status is not None:
        status = status.lower()
        if status not in STATUSES:
            print_error(f"Invalid status '{status}'. Valid statuses: {', '.join(sorted(STATUSES))}")
            raise typer.Exit(code=1)

    if priority is not None and priority not in (1, 2, 3):
        print_error(f"Invalid priority {priority}. Must be 1, 2, or 3.")
        raise typer.Exit(code=1)

    def apply_filters(tickets: list[Ticket]) -> list[Ticket]:
        result = tickets
        if assignee:
            result = [t for t in result if t.assignee == assignee]
        if tag:
            result = [t for t in result if tag in t.tags]
        return result

    def apply_priority(tickets: list[Ticket]) -> list[Ticket]:
        if priority is None:
            return tickets
        return [t for t in tickets if t.priority == priority]

    base = require_project_root()

    if backlog:
        backlog_dir = backlog_root(base) / "tickets"
        all_backlog_tickets = list_tickets(backlog_dir) if backlog_dir.exists() else []
        tickets = apply_filters(apply_priority(filter_tickets_by_status(all_backlog_tickets, status, include_closed)))

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
            typer.echo(format_ticket_summary(tickets))
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
        location_map: dict[str, str] = {}
        for location_name, tickets_dir in locations:
            tickets = list_tickets(tickets_dir)
            filtered = apply_filters(apply_priority(filter_tickets_by_status(tickets, status, include_closed)))
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
            typer.echo(format_ticket_summary(all_filtered))
    else:
        # List tickets for current branch only
        tickets_dir = get_tickets_dir(base)
        all_branch_tickets = list_tickets(tickets_dir)
        tickets = apply_filters(apply_priority(filter_tickets_by_status(all_branch_tickets, status, include_closed)))

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
            typer.echo(format_ticket_summary(tickets))


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


def render_ticket_panel(
    ticket: Ticket, ticket_path: Path, base: Path, all_tickets: list[Ticket] | None = None
) -> Panel:
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

    if ticket.parent:
        meta.add_row("parent", ticket.parent)

    if ticket.tags:
        meta.add_row("tags", ", ".join(ticket.tags))

    # Build body content (markdown)
    parts: list[object] = [meta]
    if ticket.body.strip():
        parts.append(Text())  # blank line separator
        parts.append(Markdown(ticket.body))

    # Relationship sections: blockers, blocking, children, linked
    if all_tickets is None:
        all_tickets = collect_all_tickets(base)
    relations: list[str] = []

    # Blockers: unclosed deps
    if ticket.deps:
        blockers = []
        for dep_id in ticket.deps:
            dep_status = resolve_dep_status(base, dep_id)
            if dep_status != "closed":
                blockers.append(f"- {dep_id} ({dep_status})")
        if blockers:
            relations.append("**Blockers**\n" + "\n".join(blockers))

    # Blocking: tickets that depend on this one
    blocking = [t for t in all_tickets if ticket.id in t.deps and t.status != "closed"]
    if blocking:
        lines = [f"- {t.id} ({t.status}) {t.title}" for t in blocking]
        relations.append("**Blocking**\n" + "\n".join(lines))

    # Children: tickets with this as parent
    children = [t for t in all_tickets if t.parent == ticket.id]
    if children:
        lines = [f"- {t.id} ({t.status}) {t.title}" for t in children]
        relations.append("**Children**\n" + "\n".join(lines))

    # Linked: resolve link targets
    if ticket.links:
        lines = []
        for link_id in ticket.links:
            try:
                link_result = find_ticket(base, link_id)
            except AmbiguousTicketMatch:
                link_result = None
            if link_result:
                lt, _ = link_result
                lines.append(f"- {lt.id} ({lt.status}) {lt.title}")
            else:
                lines.append(f"- {link_id} (not found)")
        relations.append("**Linked**\n" + "\n".join(lines))

    if relations:
        parts.append(Text())
        parts.append(Markdown("\n\n".join(relations)))

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
    base = require_project_root()

    # Resolve tickets to show as (Ticket, Path) pairs
    pairs: list[tuple[Ticket, Path]] = []

    if all_tickets:
        try:
            feature = resolve_current_run(base)
        except RuntimeError:
            print_error("No active session. Use `kd start` first.")
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
                print_error(f"Ticket not found: {tid}")
                raise typer.Exit(code=1)
            pairs.append(result)
    else:
        # No args: find ticket assigned to "hand"
        try:
            feature = resolve_current_run(base)
        except RuntimeError:
            print_error("No active session. Use `kd start` first.")
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
            print_error("No ticket assigned to 'hand'. Use `kd tk assign <id> hand`.")
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
        cached_tickets = collect_all_tickets(base) if len(pairs) > 1 else None
        for i, (ticket, ticket_path) in enumerate(pairs):
            if i > 0:
                console.print()  # separator between tickets
            console.print(render_ticket_panel(ticket, ticket_path, base, all_tickets=cached_tickets))


def update_ticket_status(ticket_id: str, new_status: str) -> None:
    """Helper to update a ticket's status."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
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
    base = require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError:
        print_error("No active session. Use `kd start` first.")
        raise typer.Exit(code=1) from None

    tickets_dir = branch_root(base, feature) / "tickets"
    if not tickets_dir.exists():
        print_error("No in-progress ticket on this branch.")
        raise typer.Exit(code=1)

    in_progress = [t for t in list_tickets(tickets_dir) if t.status == "in_progress"]

    if not in_progress:
        print_error("No in-progress ticket on this branch.")
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
    duplicate_of: Annotated[
        str | None, typer.Option("--duplicate-of", help="Mark as duplicate of another ticket ID.")
    ] = None,
) -> None:
    """Set ticket status to closed."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None
    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    if duplicate_of:
        # Validate target exists and is not self-referencing
        try:
            dup_result = find_ticket(base, duplicate_of)
        except AmbiguousTicketMatch as e:
            print_error(f"Duplicate target: {e}")
            raise typer.Exit(code=1) from None
        if dup_result is None:
            print_error(f"Duplicate target not found: {duplicate_of}")
            raise typer.Exit(code=1)
        dup_ticket, _ = dup_result
        if dup_ticket.id == ticket.id:
            print_error("A ticket cannot be a duplicate of itself")
            raise typer.Exit(code=1)
        ticket.duplicate_of = dup_ticket.id
        reason = reason or f"Duplicate of {dup_ticket.id}"

    old_status = ticket.status
    ticket.status = "closed"
    ticket.closed_at = datetime.now(UTC)
    write_ticket(ticket, ticket_path)

    if reason:
        from kingdom.harness import append_worklog

        append_worklog(ticket_path, f"Closed: {reason}")

    # Auto-archive: closing a backlog ticket moves it to archive/backlog/tickets/
    backlog_tickets = backlog_root(base) / "tickets"
    archive_backlog_tickets = archive_root(base) / "backlog" / "tickets"
    if ticket_path.parent.resolve() == backlog_tickets.resolve():
        ticket_path = move_ticket(ticket_path, archive_backlog_tickets)

    typer.echo(f"{ticket.id}: {old_status} → closed — {ticket.title}")

    unblocked = find_newly_unblocked(ticket.id, base)
    if unblocked:
        typer.echo("")
        typer.echo(f"Unblocked {len(unblocked)} ticket(s):")
        for t in unblocked:
            typer.echo(f"  {t.id} [P{t.priority}] — {t.title}")


@ticket_app.command("reopen", help="Reopen a closed ticket.")
def ticket_reopen(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status back to open."""
    update_ticket_status(ticket_id, "open")


@ticket_app.command("delete", help="Permanently delete a ticket file.")
def ticket_delete(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt.")] = False,
) -> None:
    """Remove a ticket file from disk."""
    base = require_project_root()
    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    # Guard: refuse to delete if a peasant is actively working on this ticket
    branch_dir = ticket_path.parent.parent  # .kd/branches/<branch> or .kd/backlog
    if branch_dir.parent.name == "branches":
        from kingdom.session import get_agent_state

        branch_name = branch_dir.name
        session_name = f"peasant-{ticket.id}"
        state = get_agent_state(base, branch_name, session_name)
        if state.status in ("working", "needs_king_review"):
            print_error(
                f"Ticket {ticket.id} has an active peasant (status: {state.status}). "
                f"Stop it first with `kd peasant stop {ticket.id}`."
            )
            raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"Delete {ticket.id} — {ticket.title}?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(code=0)

    ticket_path.unlink()
    typer.echo(f"Deleted {ticket.id} — {ticket.title}")


@ticket_app.command("dep", help="Add a dependency to a ticket.")
def ticket_dep(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    depends_on: Annotated[str, typer.Argument(help="ID of ticket this depends on.")],
) -> None:
    """Add a dependency: ticket_id depends on depends_on."""
    base = require_project_root()

    # Find both tickets
    try:
        result = find_ticket(base, ticket_id)
        dep_result = find_ticket(base, depends_on)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)
    if dep_result is None:
        print_error(f"Dependency ticket not found: {depends_on}")
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
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    # Resolve the dependency ID via find_ticket (handles partial IDs properly)
    try:
        dep_result = find_ticket(base, depends_on)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if dep_result is not None:
        dep_id = dep_result[0].id
    elif depends_on in ticket.deps:
        # Dep ticket no longer exists but is in deps list — allow exact removal
        dep_id = depends_on
    else:
        print_error(f"{ticket.id} does not depend on {depends_on}")
        raise typer.Exit(code=1)

    if dep_id not in ticket.deps:
        print_error(f"{ticket.id} does not depend on {dep_id}")
        raise typer.Exit(code=1)

    ticket.deps.remove(dep_id)
    write_ticket(ticket, ticket_path)
    typer.echo(f"{ticket.id}: removed dependency → {dep_id}")


@ticket_app.command("dep-tree", help="Show dependency tree for a ticket.")
def ticket_dep_tree(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    full: Annotated[bool, typer.Option("--full", help="Show duplicate subtrees instead of deduplicating.")] = False,
) -> None:
    """Display the dependency tree rooted at a ticket."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    all_tickets = collect_all_tickets(base)
    ticket_map = {t.id: t for t in all_tickets}

    root_ticket = result[0]
    seen: set[str] = set()

    def print_tree(tid: str, prefix: str = "", last: bool = True, ancestors: frozenset[str] = frozenset()) -> None:
        t = ticket_map.get(tid)
        connector = "└── " if last else "├── "
        label = f"{tid} [{t.status}] {t.title}" if t else f"{tid} [unknown]"

        # Always detect cycles to prevent infinite recursion
        if tid in ancestors:
            typer.echo(f"{prefix}{connector}{label} (↻ cycle)")
            return

        if not full and tid in seen:
            typer.echo(f"{prefix}{connector}{label} (↑ see above)")
            return

        typer.echo(f"{prefix}{connector}{label}")
        seen.add(tid)

        if t and t.deps:
            child_prefix = prefix + ("    " if last else "│   ")
            child_ancestors = ancestors | {tid}
            for i, dep_id in enumerate(t.deps):
                print_tree(dep_id, child_prefix, last=(i == len(t.deps) - 1), ancestors=child_ancestors)

    # Print root
    label = f"{root_ticket.id} [{root_ticket.status}] {root_ticket.title}"
    typer.echo(label)
    seen.add(root_ticket.id)
    root_ancestors = frozenset({root_ticket.id})
    for i, dep_id in enumerate(root_ticket.deps):
        print_tree(dep_id, "", last=(i == len(root_ticket.deps) - 1), ancestors=root_ancestors)


@ticket_app.command("dep-cycle", help="Detect dependency cycles.")
def ticket_dep_cycle() -> None:
    """Find and report any dependency cycles among open tickets."""
    base = require_project_root()
    all_tickets = collect_all_tickets(base)
    # Filter to non-closed tickets (open, in_progress, in_review)
    open_tickets = [t for t in all_tickets if t.status != "closed"]
    ticket_map = {t.id: t for t in open_tickets}

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t.id: WHITE for t in open_tickets}
    cycles: list[list[str]] = []

    def dfs(tid: str, path: list[str]) -> None:
        color[tid] = GRAY
        t = ticket_map.get(tid)
        if t:
            for dep_id in t.deps:
                if dep_id not in color:
                    continue
                if color[dep_id] == GRAY:
                    # Found a cycle — extract it
                    cycle_start = path.index(dep_id)
                    cycles.append([*path[cycle_start:], dep_id])
                elif color[dep_id] == WHITE:
                    dfs(dep_id, [*path, dep_id])
        color[tid] = BLACK

    for tid in color:
        if color[tid] == WHITE:
            dfs(tid, [tid])

    if not cycles:
        typer.echo("No dependency cycles found.")
    else:
        print_error(f"Found {len(cycles)} cycle(s):")
        for cycle in cycles:
            error_console.print(f"  {' → '.join(cycle)}")
        raise typer.Exit(code=1)


@ticket_app.command("blocked", help="List tickets blocked by unresolved dependencies.")
def ticket_blocked(
    assignee: Annotated[str | None, typer.Option("--assignee", "-a", help="Filter by assignee.")] = None,
    tag: Annotated[str | None, typer.Option("--tag", "-T", help="Filter by tag.")] = None,
) -> None:
    """List open tickets that have at least one unresolved dependency."""
    base = require_project_root()
    all_tickets = collect_all_tickets(base)
    status_by_id = {t.id: t.status for t in all_tickets}

    blocked = []
    for ticket in all_tickets:
        if ticket.status == "closed":
            continue
        if not ticket.deps:
            continue
        open_deps = [d for d in ticket.deps if status_by_id.get(d, "unknown") != "closed"]
        if not open_deps:
            continue
        if assignee and ticket.assignee != assignee:
            continue
        if tag and tag not in ticket.tags:
            continue
        blocked.append((ticket, open_deps))

    if not blocked:
        typer.echo("No blocked tickets.")
        return

    for ticket, open_deps in blocked:
        dep_str = ", ".join(open_deps)
        prefix = f"  {ticket.id} "
        typer.echo(f"{prefix}[P{ticket.priority}][{ticket.status}] {ticket.title}")
        typer.echo(f"{' ' * len(prefix)}blocked by: {dep_str}")


@ticket_app.command("link", help="Add symmetric links between tickets.")
def ticket_link(
    ticket_ids: Annotated[list[str], typer.Argument(help="Two or more ticket IDs to link together.")],
) -> None:
    """Create symmetric links between all given tickets."""
    if len(ticket_ids) < 2:
        print_error("Need at least two ticket IDs to link.")
        raise typer.Exit(code=1)

    base = require_project_root()

    # Resolve all tickets first, deduplicating by resolved ID
    seen_ids: dict[str, tuple[Ticket, Path]] = {}
    for tid in ticket_ids:
        try:
            result = find_ticket(base, tid)
        except AmbiguousTicketMatch as e:
            print_error(f"{e}")
            raise typer.Exit(code=1) from None
        if result is None:
            print_error(f"Ticket not found: {tid}")
            raise typer.Exit(code=1)
        seen_ids[result[0].id] = result

    resolved = list(seen_ids.values())

    if len(resolved) < 2:
        print_error("Cannot create self-link. Provide at least two distinct ticket IDs.")
        raise typer.Exit(code=1)

    # Add symmetric links
    for i, (ticket, ticket_path) in enumerate(resolved):
        changed = False
        for j, (other, _) in enumerate(resolved):
            if i != j and other.id not in ticket.links:
                ticket.links.append(other.id)
                changed = True
        if changed:
            write_ticket(ticket, ticket_path)

    ids = [t.id for t, _ in resolved]
    typer.echo(f"Linked: {' ↔ '.join(ids)}")


@ticket_app.command("unlink", help="Remove a link between two tickets.")
def ticket_unlink(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID.")],
    target_id: Annotated[str, typer.Argument(help="ID of ticket to unlink from.")],
) -> None:
    """Remove a symmetric link between two tickets."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None
    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    try:
        target_result = find_ticket(base, target_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None
    if target_result is None:
        print_error(f"Ticket not found: {target_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    target, target_path = target_result

    removed = False
    if target.id in ticket.links:
        ticket.links.remove(target.id)
        write_ticket(ticket, ticket_path)
        removed = True
    if ticket.id in target.links:
        target.links.remove(ticket.id)
        write_ticket(target, target_path)
        removed = True

    if removed:
        typer.echo(f"Unlinked: {ticket.id} ↔ {target.id}")
    else:
        typer.echo(f"No link between {ticket.id} and {target.id}")


@ticket_app.command("assign", help="Assign a ticket to an agent.")
def ticket_assign(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    agent: Annotated[str, typer.Argument(help="Agent name or 'hand' for current agent.")],
) -> None:
    """Set the assignee field on a ticket."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
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
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
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
    base = require_project_root()

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
            print_error(f"Ticket not found: {tid}")
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
    base = require_project_root()

    try:
        resolve_current_run(base)
    except RuntimeError as exc:
        print_error(str(exc))
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
            print_error(f"Ticket not found in backlog: {tid}")
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
    base = require_project_root()

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

        branch_tickets = [(t, loc) for t, loc in ready_tickets if loc != "backlog"]
        backlog_tickets_list = [(t, loc) for t, loc in ready_tickets if loc == "backlog"]

        def format_ticket(ticket: Ticket) -> str:
            return f"  {ticket.id} [P{ticket.priority}][{ticket.status}] {ticket.title}"

        if branch_tickets:
            typer.echo("Branch:")
            for ticket, _ in branch_tickets:
                typer.echo(format_ticket(ticket))
        if backlog_tickets_list:
            if branch_tickets:
                typer.echo("")
            typer.echo("Backlog:")
            for ticket, _ in backlog_tickets_list:
                typer.echo(format_ticket(ticket))


@ticket_app.command("closed", help="List recently closed tickets.")
def ticket_closed(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max tickets to show.")] = 20,
    assignee: Annotated[str | None, typer.Option("--assignee", "-a", help="Filter by assignee.")] = None,
    tag: Annotated[str | None, typer.Option("--tag", "-T", help="Filter by tag.")] = None,
) -> None:
    """List recently closed tickets across all locations, sorted by close date (newest first)."""
    base = require_project_root()
    all_tickets = collect_all_tickets(base, include_archive=True, include_done=True)

    closed = [t for t in all_tickets if t.status == "closed"]
    if assignee:
        closed = [t for t in closed if t.assignee == assignee]
    if tag:
        closed = [t for t in closed if tag in t.tags]
    closed.sort(key=lambda t: t.closed_at or t.created, reverse=True)
    closed = closed[:limit]

    if not closed:
        typer.echo("No closed tickets found.")
        return

    render_ticket_table(closed)
    typer.echo(f"{len(closed)} closed ticket(s)")


@ticket_app.command("add-note", help="Append a timestamped note to a ticket.")
def ticket_add_note(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    text: Annotated[str | None, typer.Argument(help="Note text. Reads from stdin if omitted.")] = None,
) -> None:
    """Append a timestamped note to the ticket body."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result

    if text is None:
        text = sys.stdin.read().strip()
        if not text:
            print_error("No note text provided.")
            raise typer.Exit(code=1)

    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    note = f"\n**Note ({timestamp}):** {text}\n"

    content = ticket_path.read_text(encoding="utf-8")
    if not content.endswith("\n"):
        content += "\n"
    content += note
    ticket_path.write_text(content, encoding="utf-8")

    typer.echo(f"{ticket.id}: note added")


@ticket_app.command("query", help="Output tickets as JSON with optional jq filtering.")
def ticket_query(
    jq_filter: Annotated[str | None, typer.Argument(help="Optional jq filter expression.")] = None,
) -> None:
    """Output all non-closed tickets as JSON. Pipe through jq if a filter is given."""
    base = require_project_root()
    all_tickets = collect_all_tickets(base)

    data = [
        {
            "id": t.id,
            "status": t.status,
            "priority": t.priority,
            "type": t.type,
            "title": t.title,
            "assignee": t.assignee,
            "deps": t.deps,
            "links": t.links,
            "tags": t.tags,
            "parent": t.parent,
            "created": t.created.isoformat(),
        }
        for t in all_tickets
        if t.status != "closed"
    ]

    if jq_filter:
        import shutil as sh

        if not sh.which("jq"):
            print_error("jq is not installed. Install it or omit the filter.")
            raise typer.Exit(code=1)
        proc = subprocess.run(
            ["jq", jq_filter],
            input=json.dumps(data),
            capture_output=True,
            text=True,
        )
        typer.echo(proc.stdout.rstrip())
        if proc.returncode != 0:
            typer.echo(proc.stderr.rstrip(), err=True)
            raise typer.Exit(code=proc.returncode)
    else:
        typer.echo(json.dumps(data, indent=2))


@ticket_app.command("log", help="Append a worklog entry to a ticket.")
def ticket_log(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    message: Annotated[str, typer.Argument(help="Worklog message to append.")],
) -> None:
    """Append a timestamped journal entry to the ticket's Worklog section."""
    from kingdom.ticket import append_worklog_entry

    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    ticket, ticket_path = result
    entry = append_worklog_entry(ticket_path, message)
    typer.echo(f"{ticket.id}: {entry}")


@ticket_app.command("edit", help="Open a ticket in $EDITOR.")
def ticket_edit(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Open a ticket file in the default editor."""
    base = require_project_root()

    try:
        result = find_ticket(base, ticket_id)
    except AmbiguousTicketMatch as e:
        print_error(f"{e}")
        raise typer.Exit(code=1) from None

    if result is None:
        print_error(f"Ticket not found: {ticket_id}")
        raise typer.Exit(code=1)

    import shlex

    _, ticket_path = result
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([*shlex.split(editor), str(ticket_path)])


def main() -> None:
    app()


if __name__ == "__main__":
    main()
