"""Council CLI commands."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from kingdom.thread import ThreadStatus

import click
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

from kingdom.council import create_council
from kingdom.session import get_current_thread, set_current_thread
from kingdom.state import council_logs_root, logs_root, read_json, resolve_current_run

from .display import error_console, print_error
from .helpers import require_project_root, verbose_echo

council_app = typer.Typer(name="council", help="Query council members.")


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
    continue_thread: Annotated[
        bool, typer.Option("--continue", "-c", help="Continue the current council thread.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON format.")] = False,
    async_mode: Annotated[
        bool, typer.Option("--async", help="Dispatch in background, then watch for responses.")
    ] = False,
    no_watch: Annotated[bool, typer.Option("--no-watch", help="With --async, dispatch only without watching.")] = False,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Per-model timeout in seconds.")] = None,
    writable: Annotated[
        bool, typer.Option("--writable", "-w", help="Grant council members full write permissions.")
    ] = False,
    phase: Annotated[str, typer.Option(hidden=True)] = "council",
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

    console = Console()

    c = create_council(base, feature, writable=writable, timeout=timeout, phase=phase)
    timeout = c.timeout

    verbose_echo(f"base: {base}")
    verbose_echo(f"branch: {feature}")
    verbose_echo(f"members: {', '.join(m.name for m in c.members)}")
    verbose_echo(f"timeout: {timeout}s")
    verbose_echo(f"logs: {logs_root(base, feature)}")

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

    # Determine thread: new by default, or continue current
    current = get_current_thread(base, feature)

    if continue_thread:
        # --continue: reuse existing thread, error if none exists
        if current is None or not thread_dir(base, feature, current).exists():
            print_error("No active council thread on this branch. Drop --continue to start a new one.")
            raise typer.Exit(code=1)
        thread_id = current
        start_new = False
    else:
        # Default: always start a new thread
        start_new = True
        thread_id = f"council-{secrets.token_hex(2)}"
        if to:
            member_names = [to]
        else:
            member_names = [m.name for m in c.members]
        create_thread(base, feature, thread_id, ["king", *member_names], "council")
        set_current_thread(base, feature, thread_id)

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
    feature = resolve_current_run(base)  # Validate active session

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

    # Get commit log and current branch for context
    log_result = subprocess.run(
        ["git", "log", "--oneline", f"{base_branch}..HEAD"],
        capture_output=True,
        text=True,
    )
    commits = log_result.stdout.strip()

    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
    )
    current_branch = branch_result.stdout.strip()

    # Look up current ticket for context (optional — works without one)
    ticket_title = ""
    ticket_body = ""
    ticket_path_str = ""
    worklog = ""
    try:
        from kingdom.harness import extract_worklog
        from kingdom.state import tickets_root
        from kingdom.ticket import list_tickets, read_ticket

        tdir = tickets_root(base, feature)
        in_progress = [t for t in list_tickets(tdir) if t.status == "in_progress"]
        if in_progress:
            tp = tdir / f"{in_progress[0].id}.md"
            ticket = read_ticket(tp)
            ticket_title = ticket.title
            ticket_body = ticket.body
            ticket_path_str = str(tp)
            worklog = extract_worklog(tp)
    except Exception:
        pass  # No ticket context — that's fine

    # Build the review prompt — shared with harness council review
    from kingdom.harness import build_review_prompt

    review_prompt = build_review_prompt(
        changed_files=stat_output,
        base_branch=base_branch,
        branch=current_branch,
        commits=commits,
        ticket_title=ticket_title,
        ticket_body=ticket_body,
        ticket_path=ticket_path_str,
        worklog=worklog,
    )

    # Delegate to council_ask — new thread by default now
    council_ask(
        prompt=review_prompt,
        to=to,
        json_output=False,
        async_mode=async_mode,
        no_watch=no_watch,
        writable=writable,
        phase="review",
    )


@council_app.command("reset", help="Clear council sessions.")
def council_reset(
    member_name: Annotated[str | None, typer.Option("--member", help="Reset only this member's session.")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt.")] = False,
) -> None:
    """Clear council member sessions. Use --member to reset a single member."""
    base = require_project_root()
    feature = resolve_current_run(base)

    c = create_council(base, feature)

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
def council_list(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
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
        if output_json:
            typer.echo("[]")
        else:
            typer.echo('No council threads. Start one with `kd council ask "prompt"`.')
        return

    state_symbols = {
        MEMBER_RESPONDED: ("[green]\u2713[/green]", "responded"),
        MEMBER_RUNNING: ("[yellow]\u25cb[/yellow]", "running"),
        MEMBER_ERRORED: ("[red]\u2717[/red]", "errored"),
        MEMBER_TIMED_OUT: ("[red]\u29d6[/red]", "timed out"),
        MEMBER_PENDING: ("[dim]\u2026[/dim]", "pending"),
    }

    if output_json:
        data = []
        for t in council_threads:
            messages = list_messages(base, feature, t.id)
            topic = ""
            for msg in messages:
                if msg.from_ == "king":
                    first_line = msg.body.strip().split("\n", 1)[0]
                    topic = first_line[:60] + ("\u2026" if len(first_line) > 60 else "")
                    break
            status = thread_response_status(base, feature, t.id)
            members = {}
            for name in sorted(status.member_states):
                ms = status.member_states[name]
                members[name] = ms.state
            data.append(
                {
                    "id": t.id,
                    "created_at": t.created_at.isoformat(),
                    "message_count": len(messages),
                    "topic": topic,
                    "current": t.id == current,
                    "members": members,
                }
            )
        typer.echo(json.dumps(data, indent=2))
        return

    for t in council_threads:
        marker = "[bold] *[/bold]" if t.id == current else ""
        created = t.created_at.strftime("%Y-%m-%d %H:%M")

        # Get topic from first king message
        messages = list_messages(base, feature, t.id)
        msg_count = len(messages)
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

        count_str = f"[dim]{msg_count} msg{'s' if msg_count != 1 else ''}[/dim]"
        console.print(f"[bold]{t.id}[/bold]  [dim]{created}[/dim]  {count_str}{marker}")
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
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Show which councillors have responded and which are still pending."""
    from kingdom.thread import list_threads, thread_response_status

    base = require_project_root()
    feature = resolve_current_run(base)

    def thread_status_to_dict(ts: ThreadStatus) -> dict:
        members = {}
        for name in sorted(ts.member_states):
            ms = ts.member_states[name]
            entry: dict = {"state": ms.state}
            if ms.error:
                entry["error"] = ms.error
            members[name] = entry
        return {
            "thread_id": ts.thread_id,
            "expected": sorted(ts.expected),
            "responded": sorted(ts.responded),
            "pending": sorted(ts.pending),
            "members": members,
        }

    if all_threads:
        threads = list_threads(base, feature)
        council_threads = [t for t in threads if t.pattern == "council"]
        if not council_threads:
            if output_json:
                typer.echo("[]")
            else:
                typer.echo('No council threads. Start one with `kd council ask "prompt"`.')
            return
        if output_json:
            data = []
            for t in council_threads:
                status = thread_response_status(base, feature, t.id)
                data.append(thread_status_to_dict(status))
            typer.echo(json.dumps(data, indent=2))
            return
        for t in council_threads:
            status = thread_response_status(base, feature, t.id)
            print_thread_status(status, base, feature, verbose)
            typer.echo()
        return

    # Single thread mode
    thread_id = resolve_council_thread_id(base, feature, thread_id, command="status")

    status = thread_response_status(base, feature, thread_id)
    if output_json:
        typer.echo(json.dumps(thread_status_to_dict(status), indent=2))
        return
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
    c = create_council(base, feature, timeout=timeout)
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
# kd council chat — TUI council chat
# ---------------------------------------------------------------------------


@council_app.command("chat", help="Open council chat TUI.")
def council_chat(
    thread_id: Annotated[str | None, typer.Argument(help="Thread ID to open.")] = None,
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

    Creates a new thread by default, or opens an existing one by ID.
    """
    import kingdom.cli as _cli
    from kingdom.config import load_config
    from kingdom.thread import create_thread

    base = require_project_root()
    feature = _cli.resolve_current_run(base)
    cfg = load_config(base)

    if thread_id:
        tid = resolve_council_thread_id(base, feature, thread_id, command="chat")
        set_current_thread(base, feature, tid)
    else:
        # Default: new thread (same as ask)
        tid = f"council-{secrets.token_hex(2)}"
        member_names = cfg.council.members or list(cfg.agents)
        create_thread(base, feature, tid, ["king", *member_names], "council")
        set_current_thread(base, feature, tid)

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
