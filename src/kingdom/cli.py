from __future__ import annotations

"""Command-line interface for Kingdom.

Usage example:
    kd --help
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    council_logs_root,
    ensure_run_layout,
    logs_root,
    read_json,
    resolve_current_run,
    sessions_root,
    set_current_run,
    write_json,
)
from kingdom.tmux import (
    attach_window,
    derive_server_name,
    ensure_council_layout,
    ensure_session,
    ensure_window,
    get_pane_command,
    list_panes,
    list_windows,
    send_keys,
    should_send_command,
)

app = typer.Typer(
    name="kd",
    help="Kingdom CLI.",
    add_completion=False,
)


def not_implemented(command: str) -> None:
    typer.echo(f"{command}: not implemented yet.")
    raise typer.Exit(code=1)


def hand_command() -> str:
    return f"{sys.executable} -m kingdom.hand"


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


@app.command(help="Initialize a run, state, and tmux session.")
def start(feature: str = typer.Argument(..., help="Feature name for the run.")) -> None:
    base = Path.cwd()
    paths = ensure_run_layout(base, feature)
    set_current_run(base, feature)
    ensure_feature_branch(feature)
    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_window(server, feature, "hand")
    typer.echo(f"Initialized run: {paths['run_root']}")
    typer.echo(f"Tmux: server={server} session={feature} window=hand")


@app.command(help="Attach to the Hand (persistent chat window).")
def chat() -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    ensure_run_layout(base, feature)

    log_path = logs_root(base, feature) / "hand.jsonl"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")

    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_window(server, feature, "hand")
    hand_target = f"{feature}:hand"
    panes = sorted(list_panes(server, hand_target), key=int)
    if not panes:
        raise RuntimeError("Hand window has no panes")
    pane_target = f"{hand_target}.{panes[0]}"
    current = get_pane_command(server, pane_target)
    if should_send_command(current):
        send_keys(server, pane_target, hand_command())
    attach_window(server, feature, "hand")


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
    paths = ensure_run_layout(base, feature)

    logs_dir = logs_root(base, feature)
    sessions_dir = sessions_root(base, feature)
    council_logs_dir = paths["council_logs_root"]

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
    ensure_run_layout(base, feature)

    logs_dir = logs_root(base, feature)
    sessions_dir = sessions_root(base, feature)

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


@app.command(help="Draft or view the current design doc.")
def design() -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)
    design_path = paths["design_md"]
    if design_path.read_text(encoding="utf-8").strip() == "":
        design_path.write_text(build_design_template(feature), encoding="utf-8")
        typer.echo(f"Created design template at {design_path}")
        return

    typer.echo(f"Design already exists at {design_path}")


@app.command(help="Draft or iterate the current breakdown.")
def breakdown(
    apply: bool = typer.Option(
        False, "--apply", help="Create tk tickets from breakdown.md."
    ),
) -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)
    breakdown_path = paths["breakdown_md"]
    if breakdown_path.read_text(encoding="utf-8").strip() == "":
        breakdown_path.write_text(build_breakdown_template(feature), encoding="utf-8")
        typer.echo(f"Created breakdown template at {breakdown_path}")
        return

    if not apply:
        typer.echo(f"Breakdown already exists at {breakdown_path}")
        typer.echo("Use --apply to create tk tickets from the breakdown.")
        return

    tickets = parse_breakdown_tickets(breakdown_path.read_text(encoding="utf-8"))
    if not tickets:
        raise RuntimeError("No tickets found in breakdown.md")

    created: dict[str, str] = {}
    for ticket in tickets:
        args = [
            "tk",
            "create",
            ticket["title"],
            "-p",
            str(ticket["priority"]),
        ]
        if ticket["description"]:
            args.extend(["-d", ticket["description"]])
        acceptance = "\n".join(ticket["acceptance"]).strip()
        if acceptance:
            args.extend(["--acceptance", acceptance])

        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "tk create failed")

        ticket_id = result.stdout.strip()
        created[ticket["breakdown_id"]] = ticket_id
        typer.echo(f"Created ticket {ticket_id} for {ticket['breakdown_id']}")

    for ticket in tickets:
        ticket_id = created.get(ticket["breakdown_id"])
        for dep in ticket["depends_on"]:
            dep_id = created.get(dep, dep)
            result = subprocess.run(["tk", "dep", ticket_id, dep_id], text=True)
            if result.returncode != 0:
                raise RuntimeError(f"tk dep failed for {ticket_id} -> {dep_id}")

    state = read_json(paths["state_json"])
    state["tickets"] = {**state.get("tickets", {}), **created}
    write_json(paths["state_json"], state)


@app.command(help="Start a Peasant for the given ticket.")
def peasant(ticket: str = typer.Argument(..., help="Ticket id to execute.")) -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    paths = ensure_run_layout(base, feature)
    ensure_feature_branch(feature)

    worktrees_root = paths["state_root"] / "worktrees" / feature
    worktree_path = worktrees_root / "peasant-1"
    worktrees_root.mkdir(parents=True, exist_ok=True)

    if not worktree_path.exists():
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), feature],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git worktree add failed")

    server = derive_server_name(base)
    ensure_session(server, feature)
    ensure_window(server, feature, "peasant-1", cwd=worktree_path)
    send_keys(server, f"{feature}:peasant-1", "codex")

    state = read_json(paths["state_json"])
    state["peasant"] = {"ticket": ticket, "worktree": str(worktree_path)}
    write_json(paths["state_json"], state)


@app.command(help="Reserved for broader develop phase (MVP stub).")
def dev(ticket: str | None = typer.Argument(None, help="Optional ticket id.")) -> None:
    if ticket:
        typer.echo("MVP uses `kd peasant <ticket>` for single-ticket execution.")
        raise typer.Exit(code=1)
    typer.echo("`kd dev` is reserved. Use `kd peasant <ticket>` in the MVP.")


@app.command(help="Show current phase, run, and ticket status.")
def status() -> None:
    base = Path.cwd()
    try:
        feature = resolve_current_run(base)
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    paths = ensure_run_layout(base, feature)
    state = read_json(paths["state_json"])
    typer.echo(f"Run: {feature}")
    if state:
        typer.echo(f"State: {state}")

    server = derive_server_name(base)
    try:
        windows = list_windows(server, feature)
        typer.echo(f"Tmux windows: {', '.join(windows) if windows else 'none'}")
    except RuntimeError as exc:
        typer.echo(f"Tmux: {exc}")

    tickets = state.get("tickets", {})
    if tickets:
        typer.echo("Tickets:")
        for plan_id, ticket_id in tickets.items():
            typer.echo(f"  {plan_id} -> {ticket_id}")


@app.command(help="Attach to hand/council/peasant windows.")
def attach(target: str = typer.Argument(..., help="Target window name.")) -> None:
    base = Path.cwd()
    feature = resolve_current_run(base)
    server = derive_server_name(base)
    ensure_session(server, feature)

    # Special handling for council: set up log tailing panes
    if target == "council":
        logs_dir = logs_root(base, feature)
        ensure_council_layout(server, feature)
        window_target = f"{feature}:council"
        panes = sorted(list_panes(server, window_target), key=int)

        agent_names = ["claude", "codex", "agent"]
        for pane, agent in zip(panes[:3], agent_names):
            pane_target = f"{window_target}.{pane}"
            log_file = logs_dir / f"council-{agent}.log"
            # Ensure log file exists
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.touch()

            current = get_pane_command(server, pane_target)
            if should_send_command(current):
                send_keys(server, pane_target, f"tail -f {log_file}")

        attach_window(server, feature, "council")
        return

    windows = list_windows(server, feature)
    if target not in windows:
        typer.echo(
            f"Window '{target}' not found in session '{feature}'. Available: {', '.join(windows)}"
        )
        raise typer.Exit(code=1)

    attach_window(server, feature, target)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
