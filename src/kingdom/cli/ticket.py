"""Ticket and deps CLI commands."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import click
import typer
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from kingdom.state import (
    ExecutionContext,
    archive_root,
    backlog_root,
    branch_root,
    branches_root,
    clear_ticket_execution_contexts,
    compact_context_id,
    normalize_branch_name,
    read_execution_ticket_context,
    read_terminal_ticket_context,
    record_execution_ticket_context,
    record_terminal_ticket_context,
    resolve_current_run,
    resolve_execution_context,
)
from kingdom.ticket import (
    STATUSES,
    TICKET_RESOLUTIONS,
    TICKET_TYPES,
    AmbiguousTicketMatch,
    Ticket,
    append_worklog_entry,
    collect_all_tickets,
    collect_tickets_by_location,
    effective_resolution,
    filter_tickets,
    filter_tickets_by_deps,
    filter_tickets_by_status,
    find_newly_unblocked,
    find_ticket,
    generate_ticket_id,
    insert_markdown_section_entry,
    list_tickets,
    move_ticket,
    read_ticket,
    write_ticket,
)

from .display import STATUS_COLORS, STATUS_STYLES, console_width, error_console, print_error
from .helpers import (
    peasant_session_name,
    require_project_root,
    resolve_ticket_or_exit,
)

ticket_app = typer.Typer(name="ticket", help="Manage tickets.")

# Dependency management sub-app
deps_app = typer.Typer(name="deps", help="Manage ticket dependencies.")
ticket_app.add_typer(deps_app, name="deps")


def get_tickets_dir(base: Path, backlog: bool = False) -> Path:
    """Get the tickets directory for the current context."""
    if backlog:
        return backlog_root(base) / "tickets"

    # Try to get current branch's tickets directory
    try:
        feature = resolve_current_run(base)
        return branch_root(base, feature) / "tickets"
    except RuntimeError:
        # No active branch, use backlog
        return backlog_root(base) / "tickets"


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
    assignee_str = f" @{compact_context_id(ticket.assignee)}" if ticket.assignee else ""
    location_str = f" ({location})" if location else ""
    dep_str = f"  <- {', '.join(ticket.deps)}" if ticket.deps else ""
    return f"{ticket.id} [P{ticket.priority}][{ticket.status}]{assignee_str} - {ticket.title}{location_str}{dep_str}"


def format_dep(dep_id: str, status_by_id: dict[str, str]) -> str:
    """Format a single dependency ID with a status indicator.

    Closed deps get a checkmark (e.g. ``5afc ✓``), open/unknown deps are plain.
    """
    if status_by_id.get(dep_id) == "closed":
        return f"{dep_id} ✓"
    return dep_id


def render_ticket_table(
    tickets: list[Ticket],
    *,
    show_location: bool = False,
    locations: dict[str, str] | None = None,
    status_by_id: dict[str, str] | None = None,
) -> None:
    """Render a list of tickets as a Rich table.

    Only shows Assignee, Deps, and Location columns when at least one ticket
    has data for that column, keeping the table compact.

    Args:
        tickets: Tickets to display.
        show_location: Whether to include a Location column.
        locations: Mapping of ticket id -> location label (used with show_location).
        status_by_id: Mapping of ticket id -> status string for dep annotation.
    """
    has_assignee = any(t.assignee for t in tickets)
    has_deps = any(t.deps for t in tickets)
    has_resolution = any(effective_resolution(ticket) for ticket in tickets)
    dep_statuses = status_by_id or {}

    console = Console(width=max(console_width(), 120))
    table = Table(show_header=True, header_style="bold", padding=(0, 1))

    table.add_column("ID", style="cyan", no_wrap=True, min_width=4)
    table.add_column("P", justify="center", no_wrap=True, min_width=2)
    table.add_column("Status", no_wrap=True, min_width=11)
    if has_resolution:
        table.add_column("Resolution", no_wrap=True)
    if has_assignee:
        table.add_column("Assignee", no_wrap=True)
    table.add_column("Title")
    if has_deps:
        table.add_column("Deps", style="dim", no_wrap=True)
    if show_location:
        table.add_column("Location", no_wrap=True)

    for ticket in tickets:
        status_style = STATUS_STYLES.get(ticket.status, "")
        dep_str = ", ".join(format_dep(d, dep_statuses) for d in ticket.deps) if ticket.deps else ""
        assignee_str = f"@{compact_context_id(ticket.assignee)}" if ticket.assignee else ""

        row: list[str] = [
            ticket.id,
            f"P{ticket.priority}",
            f"[{status_style}]{ticket.status}[/{status_style}]" if status_style else ticket.status,
        ]
        if has_resolution:
            row.append(effective_resolution(ticket) or "")
        if has_assignee:
            row.append(assignee_str)
        title_display = f"[dim]\\[epic][/dim] {ticket.title}" if ticket.type == "epic" else ticket.title
        row.append(title_display)
        if has_deps:
            row.append(dep_str)
        if show_location:
            loc = (locations or {}).get(ticket.id, "")
            row.append(loc)

        table.add_row(*row)

    console.print(table)


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


def ticket_to_json(t: Ticket, *, detailed: bool = False, base: Path | None = None, path: Path | None = None) -> dict:
    """Serialize a ticket to a JSON-friendly dict.

    With ``detailed=True``, includes body, path, and enriched deps ``[{id, status}]``.
    """
    data: dict = {
        "id": t.id,
        "status": t.status,
        "priority": t.priority,
        "type": t.type,
        "title": t.title,
        "assignee": t.assignee,
        "deps": ([{"id": d, "status": resolve_dep_status(base, d)} for d in t.deps] if detailed and base else t.deps),
        "links": t.links,
        "tags": t.tags,
        "parent": t.parent,
        "created": t.created.isoformat(),
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "resolution": effective_resolution(t),
        "close_reason": t.close_reason,
        "closed_context": t.closed_context,
        "duplicate_of": t.duplicate_of,
        "superseded_by": t.superseded_by,
    }
    if detailed:
        data["body"] = t.body
        if path is not None:
            data["path"] = str(path)
    return data


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

    resolution = effective_resolution(ticket)
    if resolution:
        meta.add_row("resolution", resolution)
    if ticket.close_reason:
        meta.add_row("close reason", ticket.close_reason)
    if ticket.closed_at:
        meta.add_row("closed", ticket.closed_at.isoformat())
    if ticket.closed_context:
        meta.add_row("closed context", ticket.closed_context)
    if ticket.duplicate_of:
        meta.add_row("duplicate of", ticket.duplicate_of)
    if ticket.superseded_by:
        meta.add_row("superseded by", ticket.superseded_by)

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
        closed_count = sum(1 for t in children if t.status == "closed")
        header = f"**Children** ({closed_count}/{len(children)} closed)"
        lines = [f"- {t.id} ({t.status}) {t.title}" for t in children]
        relations.append(header + "\n" + "\n".join(lines))

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


@ticket_app.command("create", help="Create a new ticket.")
def ticket_create(
    title: Annotated[str | None, typer.Argument(help="Ticket title.")] = None,
    short_title_or_type: Annotated[
        str | None,
        typer.Option("-t", help="Ticket title. With a positional title, treated as legacy ticket type."),
    ] = None,
    title_option: Annotated[str | None, typer.Option("--title", help="Ticket title.")] = None,
    description: Annotated[str | None, typer.Option("-d", "--description", help="Ticket description.")] = None,
    body_text: Annotated[str | None, typer.Option("-b", "--body", help="Ticket description/body.")] = None,
    priority: Annotated[str, typer.Option("-p", "--priority", help="Priority (0-3 or p0-p3, 0 is highest).")] = "2",
    ticket_type: Annotated[str, typer.Option("--type", help="Ticket type (task, bug, feature, epic).")] = "task",
    backlog: Annotated[bool, typer.Option("--backlog", help="Create in backlog instead of current branch.")] = False,
    dep: Annotated[list[str] | None, typer.Option("--dep", help="Ticket ID(s) this depends on.")] = None,
    parent: Annotated[str | None, typer.Option("--parent", help="Parent ticket ID.")] = None,
    tags: Annotated[str | None, typer.Option("--tags", help="Comma-separated tags.")] = None,
    ac: Annotated[list[str] | None, typer.Option("--ac", help="Acceptance criteria (repeatable).")] = None,
) -> None:
    """Create a new ticket in the current branch or backlog."""
    from kingdom.state import ensure_base_layout

    base = require_project_root()

    if title and title_option:
        print_error("Provide the ticket title either positionally or with --title, not both.")
        raise typer.Exit(code=1)

    if title_option and short_title_or_type:
        print_error("Provide the ticket title with either -t or --title, not both.")
        raise typer.Exit(code=1)

    if title and short_title_or_type:
        if ticket_type != "task":
            print_error("Provide ticket type with either legacy -t shorthand or --type, not both.")
            raise typer.Exit(code=1)
        ticket_type = short_title_or_type
    elif title_option:
        title = title_option
    elif short_title_or_type:
        title = short_title_or_type

    if not title:
        print_error("Missing ticket title. Provide it positionally or with -t/--title.")
        raise typer.Exit(code=1)

    if description and body_text:
        print_error("Provide ticket body with either --description or --body, not both.")
        raise typer.Exit(code=1)
    description = description or body_text

    # Parse and validate priority (accepts 0-3, p0-p3, P0-P3)
    from kingdom.ticket import clamp_priority

    try:
        priority_int = clamp_priority(priority)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

    if ticket_type not in TICKET_TYPES:
        print_error(f"Invalid type '{ticket_type}'. Valid types: {', '.join(sorted(TICKET_TYPES))}")
        raise typer.Exit(code=1)

    # Ensure base layout exists
    ensure_base_layout(base)

    tickets_dir = get_tickets_dir(base, backlog=backlog)
    tickets_dir.mkdir(parents=True, exist_ok=True)

    # Resolve dependency IDs
    resolved_deps: list[str] = []
    if dep:
        for dep_id in dep:
            dep_ticket, _ = resolve_ticket_or_exit(base, dep_id, not_found_label="Dependency ticket not found")
            resolved_deps.append(dep_ticket.id)

    # Resolve parent
    resolved_parent = None
    if parent:
        parent_ticket, _ = resolve_ticket_or_exit(base, parent, not_found_label="Parent ticket not found")
        resolved_parent = parent_ticket.id

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Generate unique ID
    ticket_id = generate_ticket_id(tickets_dir)

    # Build body with acceptance criteria section
    body = description or ""
    ac_items = ac or []
    ac_lines = "\n".join(f"- [ ] {item}" for item in ac_items) if ac_items else "- [ ]"
    if body:
        body = f"{body}\n\n## Acceptance Criteria\n\n{ac_lines}"
    else:
        body = f"## Acceptance Criteria\n\n{ac_lines}"

    # Create ticket
    ticket = Ticket(
        id=ticket_id,
        status="open",
        deps=resolved_deps,
        links=[],
        created=datetime.now(UTC),
        type=ticket_type,
        priority=priority_int,
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


@ticket_app.command("ls", help="List tickets.", hidden=True)
@ticket_app.command("list", help="List tickets.")
def ticket_list(
    all_tickets: Annotated[bool, typer.Option("--all", "-a", help="List all tickets across all locations.")] = False,
    include_done: Annotated[
        bool, typer.Option("--include-done", help="Include tickets from done branches (with --all).")
    ] = False,
    include_closed: Annotated[bool, typer.Option("--closed", help="Include closed tickets in output.")] = False,
    recently_closed: Annotated[
        bool,
        typer.Option("--recently-closed", "--recent", help="Show closed tickets ordered by most recent closure."),
    ] = False,
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Limit the number of tickets shown.")] = None,
    ready: Annotated[bool, typer.Option("--ready", help="Show only tickets ready to work (no open deps).")] = False,
    blocked: Annotated[bool, typer.Option("--blocked", help="Show only tickets blocked by open deps.")] = False,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            "-s",
            help="Filter by status (open, in_progress, in_review, closed).",
        ),
    ] = None,
    resolution: Annotated[
        str | None,
        typer.Option(
            "--resolution",
            help="Filter closed tickets by resolution.",
            click_type=click.Choice(TICKET_RESOLUTIONS),
        ),
    ] = None,
    priority: Annotated[
        int | None,
        typer.Option("--priority", "-p", help="Filter by priority (0-3)."),
    ] = None,
    backlog: Annotated[bool, typer.Option("--backlog", help="List open tickets in backlog only.")] = False,
    assignee: Annotated[str | None, typer.Option("--assignee", "-A", help="Filter by assignee.")] = None,
    tag: Annotated[str | None, typer.Option("--tag", "-T", help="Filter by tag.")] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON (full ticket schema).")] = False,
    jq_filter: Annotated[str | None, typer.Option("--jq", help="Apply a jq filter (implies --json).")] = None,
    parent_id: Annotated[str | None, typer.Option("--parent", help="Show only children of this ticket.")] = None,
) -> None:
    """List tickets in the current branch or all locations."""
    if ready and blocked:
        print_error("--ready and --blocked are mutually exclusive.")
        raise typer.Exit(code=1)

    if recently_closed and (ready or blocked):
        print_error("--recently-closed cannot be combined with --ready or --blocked.")
        raise typer.Exit(code=1)

    if limit is not None and limit < 1:
        print_error("--limit must be 1 or greater.")
        raise typer.Exit(code=1)

    # --jq implies --json
    if jq_filter:
        output_json = True

    if status is not None:
        status = status.lower()
        if status not in STATUSES:
            print_error(f"Invalid status '{status}'. Valid statuses: {', '.join(sorted(STATUSES))}")
            raise typer.Exit(code=1)

    if resolution is not None:
        if status is not None and status != "closed":
            print_error("--resolution can only be combined with --status closed.")
            raise typer.Exit(code=1)
        include_closed = True

    if recently_closed:
        if status is not None and status != "closed":
            print_error("--recently-closed can only be combined with --status closed.")
            raise typer.Exit(code=1)
        status = "closed"
        include_closed = True

    if priority is not None and priority not in (0, 1, 2, 3):
        print_error(f"Invalid priority {priority}. Must be 0, 1, 2, or 3.")
        raise typer.Exit(code=1)

    def order_and_limit(tickets: list[Ticket]) -> list[Ticket]:
        if recently_closed:
            tickets = sorted(tickets, key=lambda ticket: ticket.closed_at or ticket.created, reverse=True)
        if limit is not None:
            tickets = tickets[:limit]
        return tickets

    def apply_all_filters(tickets: list[Ticket], status_by_id: dict[str, str]) -> list[Ticket]:
        filtered = filter_tickets_by_status(tickets, status, include_closed)
        if resolution:
            filtered = [ticket for ticket in filtered if effective_resolution(ticket) == resolution]
        filtered = filter_tickets(filtered, assignee=assignee, tag=tag, priority=priority)
        filtered = filter_tickets_by_deps(filtered, status_by_id, ready=ready, blocked=blocked)
        if resolved_parent_id:
            filtered = [t for t in filtered if t.parent == resolved_parent_id]
        return order_and_limit(filtered)

    def output_tickets_json(tickets: list[Ticket], location_map: dict[str, str] | None = None) -> None:
        """Output tickets as JSON, optionally piping through jq."""
        data = []
        for t in tickets:
            d = ticket_to_json(t)
            if location_map and t.id in location_map:
                d["location"] = location_map[t.id]
            data.append(d)
        if jq_filter:
            import shutil as sh

            if not sh.which("jq"):
                print_error("jq is not installed. Install it or omit the --jq filter.")
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

    base = require_project_root()

    # Resolve --parent to a full ticket ID; --parent implies --all
    resolved_parent_id: str | None = None
    if parent_id:
        parent_ticket, _ = resolve_ticket_or_exit(base, parent_id, not_found_label="Parent ticket not found")
        resolved_parent_id = parent_ticket.id
        all_tickets = True

    # Build a global status lookup for dep-based filtering and dep annotations.
    # Always include done branches so deps in done branches get correct ✓ marks.
    all_known_tickets = collect_all_tickets(base, include_archive=recently_closed, include_done=True)
    status_by_id = {t.id: t.status for t in all_known_tickets}

    if backlog:
        backlog_dir = backlog_root(base) / "tickets"
        backlog_pairs: list[tuple[str, Ticket]] = []
        if backlog_dir.exists():
            backlog_pairs.extend(("backlog", ticket) for ticket in list_tickets(backlog_dir))
        if recently_closed:
            archive_backlog_dir = archive_root(base) / "backlog" / "tickets"
            if archive_backlog_dir.exists():
                backlog_pairs.extend(("archive:backlog", ticket) for ticket in list_tickets(archive_backlog_dir))
        all_backlog_tickets = [ticket for _, ticket in backlog_pairs]
        tickets = apply_all_filters(all_backlog_tickets, status_by_id)
        filtered_ids = {ticket.id for ticket in tickets}
        location_map = {
            ticket.id: location_name for location_name, ticket in backlog_pairs if ticket.id in filtered_ids
        }

        if output_json:
            output_tickets_json(tickets, location_map)
        else:
            if not tickets:
                if recently_closed:
                    typer.echo("No recently closed backlog tickets.")
                elif (closed_count := sum(1 for t in all_backlog_tickets if t.status == "closed")) and (
                    not include_closed and status is None and not ready and not blocked
                ):
                    typer.echo(f"No open backlog tickets ({closed_count} closed). Use --closed to show them.")
                else:
                    typer.echo('No backlog tickets. Create one with `kd tk create --backlog "title"`.')
                return
            render_ticket_table(tickets, status_by_id=status_by_id)
            typer.echo(format_ticket_summary(tickets))
        return

    if all_tickets:
        pairs = collect_tickets_by_location(base, include_archive=recently_closed, include_done=include_done)
        all_filtered: list[Ticket] = []
        location_map: dict[str, str] = {}
        for location_name, ticket in pairs:
            location_map[ticket.id] = location_name
            all_filtered.append(ticket)
        all_filtered = apply_all_filters(all_filtered, status_by_id)
        # Re-build location_map for only the filtered set
        filtered_ids = {t.id for t in all_filtered}
        location_map = {tid: loc for tid, loc in location_map.items() if tid in filtered_ids}

        if output_json:
            output_tickets_json(all_filtered, location_map)
        else:
            if not all_filtered:
                if recently_closed:
                    typer.echo("No recently closed tickets found across any branch or backlog.")
                elif (closed_count := sum(1 for _, t in pairs if t.status == "closed")) and (
                    not include_closed and status is None and not ready and not blocked
                ):
                    typer.echo(f"No open tickets ({closed_count} closed). Use --closed to show them.")
                else:
                    typer.echo('No tickets found across any branch or backlog. Create one with `kd tk create "title"`.')
                return
            render_ticket_table(all_filtered, show_location=True, locations=location_map, status_by_id=status_by_id)
            typer.echo(format_ticket_summary(all_filtered))
    else:
        # List tickets for current branch only
        tickets_dir = get_tickets_dir(base)
        all_branch_tickets = list_tickets(tickets_dir)
        tickets = apply_all_filters(all_branch_tickets, status_by_id)

        if output_json:
            output_tickets_json(tickets)
        else:
            if not tickets:
                if recently_closed:
                    typer.echo("No recently closed tickets found on this branch.")
                elif (closed_count := sum(1 for t in all_branch_tickets if t.status == "closed")) and (
                    not include_closed and status is None and not ready and not blocked
                ):
                    typer.echo(f"No open tickets ({closed_count} closed). Use --closed to show them.")
                else:
                    typer.echo('No tickets found. Create one with `kd tk create "title"`.')
                return
            render_ticket_table(tickets, status_by_id=status_by_id)
            typer.echo(format_ticket_summary(tickets))


@ticket_app.command("show", help="Show a ticket.")
def ticket_show(
    ticket_ids: Annotated[
        list[str] | None, typer.Argument(help="Ticket ID(s) (full or partial). Omit to show ticket assigned to 'hand'.")
    ] = None,
    all_tickets: Annotated[bool, typer.Option("--all", "-a", help="Show all tickets on the current branch.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    rich: Annotated[bool, typer.Option("--rich", help="Render the human-friendly Rich panel view.")] = False,
) -> None:
    """Display one or more tickets as raw Markdown by default.

    Use --rich for the framed human view. With no args, shows the ticket assigned to 'hand'.
    """
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
            pairs.append(resolve_ticket_or_exit(base, tid))
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
            ticket_to_json(ticket, detailed=True, base=base, path=ticket_path) for ticket, ticket_path in pairs
        ]
        typer.echo(json.dumps(results_json if len(results_json) > 1 else results_json[0], indent=2))
    elif rich:
        console = Console()
        cached_tickets = collect_all_tickets(base) if len(pairs) > 1 else None
        for i, (ticket, ticket_path) in enumerate(pairs):
            if i > 0:
                console.print()  # separator between tickets
            console.print(render_ticket_panel(ticket, ticket_path, base, all_tickets=cached_tickets))
    else:
        for i, (_, ticket_path) in enumerate(pairs):
            if i > 0:
                typer.echo()
            typer.echo(ticket_path.read_text(encoding="utf-8").rstrip())
            typer.echo()
            typer.echo(f"File: {ticket_path.resolve()}")


@ticket_app.command("find", help="Find a ticket file by ID.")
def ticket_find(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Print the full path to a ticket file."""
    base = require_project_root()
    _, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    typer.echo(ticket_path.resolve())


def update_ticket_status(ticket_id: str, new_status: str, *, assignee: str | None = None) -> Ticket:
    """Helper to update a ticket's status."""
    base = require_project_root()

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    old_status = ticket.status
    ticket.status = new_status
    if assignee is not None:
        ticket.assignee = assignee
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

    return ticket


def terminal_context_location_for_start(base: Path, ticket_path: Path) -> str:
    backlog_tickets = (backlog_root(base) / "tickets").resolve()
    archive_backlog_tickets = (archive_root(base) / "backlog" / "tickets").resolve()
    ticket_parent = ticket_path.parent.resolve()

    if ticket_parent in (backlog_tickets, archive_backlog_tickets):
        return "backlog"

    archive = archive_root(base).resolve()
    try:
        archived = ticket_parent.relative_to(archive)
    except ValueError:
        pass
    else:
        if len(archived.parts) >= 2 and archived.parts[1] == "tickets":
            return f"archive:{archived.parts[0]}"

    branches = branches_root(base).resolve()
    try:
        relative = ticket_parent.relative_to(branches)
    except ValueError:
        return f"branch:{normalize_branch_name(resolve_current_run(base))}"

    if len(relative.parts) >= 2 and relative.parts[1] == "tickets":
        return f"branch:{relative.parts[0]}"
    return f"branch:{normalize_branch_name(resolve_current_run(base))}"


def ticket_from_execution_binding(base: Path, binding: dict[str, Any]) -> tuple[Ticket, Path] | None:
    ticket_id = binding.get("ticket_id")
    location = binding.get("location")
    feature = binding.get("feature")
    if not isinstance(ticket_id, str) or not ticket_id:
        return None

    if location == "backlog":
        tickets_dir = backlog_root(base) / "tickets"
    elif isinstance(location, str) and location.startswith("archive:"):
        tickets_dir = archive_root(base) / location.removeprefix("archive:") / "tickets"
    elif isinstance(location, str) and location.startswith("branch:"):
        tickets_dir = branch_root(base, location.removeprefix("branch:")) / "tickets"
    elif isinstance(feature, str) and feature:
        tickets_dir = branch_root(base, feature) / "tickets"
    else:
        return None

    for filename in (f"{ticket_id}.md", f"kin-{ticket_id}.md"):
        ticket_path = tickets_dir / filename
        try:
            ticket = read_ticket(ticket_path)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if ticket.id == ticket_id:
            return ticket, ticket_path
    return None


def unassign_previous_context_ticket(base: Path, context_id: str, previous_ticket_id: str, new_ticket_id: str) -> None:
    if previous_ticket_id == new_ticket_id:
        return
    try:
        result = find_ticket(base, previous_ticket_id)
    except AmbiguousTicketMatch:
        return
    if result is None or result.ticket.assignee != context_id:
        return
    result.ticket.assignee = None
    write_ticket(result.ticket, result.path)


class AmbiguousLegacyTickets(RuntimeError):
    def __init__(self, ticket_ids: list[str]) -> None:
        self.ticket_ids = ticket_ids
        super().__init__(f"Multiple legacy in-progress tickets: {', '.join(ticket_ids)}")


def migrate_ticket_to_execution_context(
    base: Path,
    context: ExecutionContext,
    ticket: Ticket,
    ticket_path: Path,
    *,
    feature: str,
    location: str,
) -> dict[str, Any]:
    ticket.assignee = context.context_id
    write_ticket(ticket, ticket_path)
    record_execution_ticket_context(base, context, ticket.id, feature=feature, location=location)
    binding = read_execution_ticket_context(base, context)
    if binding is None:
        raise RuntimeError(f"Failed to record execution context for ticket {ticket.id}")
    return binding


def migrate_legacy_execution_binding(
    base: Path,
    context: ExecutionContext,
    feature: str,
) -> dict[str, Any] | None:
    normalized_feature = normalize_branch_name(feature)
    legacy_binding = read_terminal_ticket_context(base)
    if legacy_binding and legacy_binding.get("feature") == normalized_feature:
        bound_ticket = ticket_from_execution_binding(base, legacy_binding)
        if bound_ticket:
            ticket, ticket_path = bound_ticket
            if ticket.status == "in_progress" and not (ticket.assignee or "").startswith("peasant-"):
                return migrate_ticket_to_execution_context(
                    base,
                    context,
                    ticket,
                    ticket_path,
                    feature=feature,
                    location=legacy_binding.get("location") or f"branch:{normalized_feature}",
                )

    tickets_dir = branch_root(base, feature) / "tickets"
    candidates = [
        ticket
        for ticket in list_tickets(tickets_dir)
        if ticket.status == "in_progress" and ticket.assignee in (None, "hand")
    ]
    if len(candidates) > 1:
        raise AmbiguousLegacyTickets(sorted(ticket.id for ticket in candidates))
    if not candidates:
        return None

    ticket = candidates[0]
    return migrate_ticket_to_execution_context(
        base,
        context,
        ticket,
        tickets_dir / f"{ticket.id}.md",
        feature=feature,
        location=f"branch:{normalized_feature}",
    )


@ticket_app.command("start", help="Mark a ticket as in_progress.")
def ticket_start(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Set ticket status to in_progress and bind it to this execution context."""
    base = require_project_root()
    try:
        feature = resolve_current_run(base)
    except RuntimeError:
        print_error("No active session. Use `kd start` first.")
        raise typer.Exit(code=1) from None

    try:
        context = resolve_execution_context()
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None
    if context is None:
        print_error("No execution context detected. Set KD_CONTEXT before starting a ticket.")
        raise typer.Exit(code=1)

    _, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    location = terminal_context_location_for_start(base, ticket_path)
    previous_binding = read_execution_ticket_context(base, context)
    if previous_binding:
        previous_ticket_id = previous_binding["ticket_id"]
        unassign_previous_context_ticket(base, context.context_id, previous_ticket_id, ticket_id)

    ticket = update_ticket_status(ticket_id, "in_progress", assignee=context.context_id)
    clear_ticket_execution_contexts(base, ticket.id)
    record_execution_ticket_context(base, context, ticket.id, feature=feature, location=location)
    record_terminal_ticket_context(base, ticket.id, feature=feature, location=location)


@ticket_app.command("current", help="Show the ticket bound to this execution context.")
def ticket_current(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    id_only: Annotated[bool, typer.Option("--id", help="Print only the ticket ID.")] = False,
    exclude_peasant: Annotated[
        bool, typer.Option("--exclude-peasant", help="Skip peasant-assigned tickets; fall back to epic.")
    ] = False,
    branch_fallback: Annotated[
        bool,
        typer.Option("--branch-fallback", help="Explicitly choose the first in-progress ticket on the branch."),
    ] = False,
) -> None:
    """Find and display the ticket bound to the calling execution context."""
    base = require_project_root()

    try:
        feature = resolve_current_run(base)
    except RuntimeError:
        if id_only:
            raise typer.Exit(code=1) from None
        print_error("No active session. Use `kd start` first.")
        raise typer.Exit(code=1) from None

    if branch_fallback:
        tickets_dir = branch_root(base, feature) / "tickets"
        in_progress = list_tickets(tickets_dir) if tickets_dir.exists() else []
        in_progress = [ticket for ticket in in_progress if ticket.status == "in_progress"]
        if exclude_peasant:
            in_progress = [ticket for ticket in in_progress if not (ticket.assignee or "").startswith("peasant-")]
        if not in_progress:
            if id_only:
                raise typer.Exit(code=1)
            print_error("No in-progress ticket on this branch.")
            raise typer.Exit(code=1)
        ticket = in_progress[0]
        ticket_path = tickets_dir / f"{ticket.id}.md"
    else:
        try:
            context = resolve_execution_context()
        except ValueError as exc:
            if id_only:
                raise typer.Exit(code=1) from None
            print_error(str(exc))
            raise typer.Exit(code=1) from None
        if context is None:
            if id_only:
                raise typer.Exit(code=1)
            print_error("No execution context detected. Set KD_CONTEXT or use --branch-fallback.")
            raise typer.Exit(code=1)

        binding = read_execution_ticket_context(base, context)
        if binding is None:
            try:
                binding = migrate_legacy_execution_binding(base, context, feature)
            except AmbiguousLegacyTickets as exc:
                if id_only:
                    raise typer.Exit(code=1) from None
                ticket_list = ", ".join(exc.ticket_ids)
                print_error(
                    f"Multiple legacy in-progress tickets ({ticket_list}); refusing to guess. "
                    "Run `kd tk start <id>` to bind this context explicitly."
                )
                raise typer.Exit(code=1) from None
        if binding is None or binding.get("feature") != normalize_branch_name(feature):
            if id_only:
                raise typer.Exit(code=1)
            print_error("No ticket bound to this execution context. Run `kd tk start <id>` or use `--branch-fallback`.")
            raise typer.Exit(code=1)

        bound_ticket = ticket_from_execution_binding(base, binding)
        if bound_ticket is None:
            if id_only:
                raise typer.Exit(code=1)
            print_error(f"Bound ticket {binding['ticket_id']} cannot be found. Run `kd tk start <id>` to recover.")
            raise typer.Exit(code=1)
        ticket, ticket_path = bound_ticket
        wrong_assignee = ticket.assignee != context.context_id
        excluded = exclude_peasant and (ticket.assignee or "").startswith("peasant-")
        if ticket.status != "in_progress" or wrong_assignee or excluded:
            if id_only:
                raise typer.Exit(code=1)
            print_error(
                f"Bound ticket {ticket.id} is no longer active for this execution context. "
                "Run `kd tk start <id>` to recover."
            )
            raise typer.Exit(code=1)
        record_execution_ticket_context(
            base,
            context,
            ticket.id,
            feature=feature,
            location=binding.get("location"),
        )

    if id_only:
        typer.echo(ticket.id)
        return

    if output_json:
        result_json = ticket_to_json(ticket, detailed=True, base=base, path=ticket_path)
        typer.echo(json.dumps(result_json, indent=2))
    else:
        console = Console()
        console.print(f"[dim]{ticket_path.relative_to(base)}[/dim]")
        console.print(Rule(style="dim"))

        status_color = STATUS_COLORS.get(ticket.status, "white")
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
                dep_color = STATUS_COLORS.get(dep_status, "white")
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
    superseded_by: Annotated[
        str | None, typer.Option("--superseded-by", help="Mark as superseded by another ticket ID.")
    ] = None,
    resolution: Annotated[
        str | None,
        typer.Option(
            "--resolution",
            help="Closure outcome: completed, wont-do, duplicate, superseded, or invalid.",
            click_type=click.Choice(TICKET_RESOLUTIONS),
        ),
    ] = None,
) -> None:
    """Close a ticket with an explicit terminal outcome."""
    base = require_project_root()

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    reason = reason.strip() if reason else None

    if duplicate_of and superseded_by:
        print_error("--duplicate-of and --superseded-by are mutually exclusive.")
        raise typer.Exit(code=1)
    if duplicate_of and resolution not in (None, "duplicate"):
        print_error(
            f"--duplicate-of requires --resolution duplicate, not {resolution}. "
            "Use --resolution duplicate or omit --resolution."
        )
        raise typer.Exit(code=1)
    if superseded_by and resolution not in (None, "superseded"):
        print_error(
            f"--superseded-by requires --resolution superseded, not {resolution}. "
            "Use --resolution superseded or omit --resolution."
        )
        raise typer.Exit(code=1)

    duplicate_target_id = None
    if duplicate_of:
        dup_ticket, _ = resolve_ticket_or_exit(base, duplicate_of, not_found_label="Duplicate target not found")
        if dup_ticket.id == ticket.id:
            print_error("A ticket cannot be a duplicate of itself")
            raise typer.Exit(code=1)
        duplicate_target_id = dup_ticket.id

    superseding_ticket_id = None
    if superseded_by:
        superseding_ticket, _ = resolve_ticket_or_exit(
            base,
            superseded_by,
            not_found_label="Superseding ticket not found",
        )
        if superseding_ticket.id == ticket.id:
            print_error("A ticket cannot be superseded by itself")
            raise typer.Exit(code=1)
        superseding_ticket_id = superseding_ticket.id

    existing_resolution = effective_resolution(ticket) or "completed"
    close_resolution = resolution
    if close_resolution is None:
        if duplicate_target_id:
            close_resolution = "duplicate"
        elif superseding_ticket_id:
            close_resolution = "superseded"
        elif ticket.status == "closed":
            close_resolution = existing_resolution
        else:
            close_resolution = "completed"

    if ticket.status == "closed":
        changed_duplicate_target = duplicate_target_id is not None and duplicate_target_id != ticket.duplicate_of
        changed_superseding_ticket = superseding_ticket_id is not None and superseding_ticket_id != ticket.superseded_by
        if close_resolution != existing_resolution or changed_duplicate_target or changed_superseding_ticket or reason:
            print_error(
                f"Ticket {ticket.id} is already closed with resolution {existing_resolution}. "
                f"Run `kd tk reopen {ticket.id}` before changing its closure details."
            )
            raise typer.Exit(code=1)
        typer.echo(f"{ticket.id}: already closed ({existing_resolution}) — {ticket.title}")
        return

    # Block closing an epic with open children
    if ticket.type == "epic":
        all_known = collect_all_tickets(base)
        open_children = [t for t in all_known if t.parent == ticket.id and t.status != "closed"]
        if open_children:
            print_error(f"Cannot close epic {ticket.id}: {len(open_children)} child ticket(s) still open")
            for child in open_children:
                error_console.print(f"  {child.id} ({child.status}) {child.title}")
            raise typer.Exit(code=1)

    if duplicate_target_id:
        reason = reason or f"Duplicate of {duplicate_target_id}"
    if superseding_ticket_id:
        reason = reason or f"Superseded by {superseding_ticket_id}"

    if close_resolution != "completed" and not reason:
        print_error(
            f"Resolution {close_resolution} requires a non-empty --reason. "
            f'Retry with `kd tk close {ticket.id} --resolution {close_resolution} --reason "..."`.'
        )
        raise typer.Exit(code=1)

    # Warn if an active peasant is working on this ticket
    try:
        feature = resolve_current_run(base)
        from kingdom.session import list_active_agents

        active = list_active_agents(base, feature)
        active_peasants = [
            a
            for a in active
            if a.name.startswith("peasant-") and a.ticket == ticket.id and a.status not in ("done", "failed", "stopped")
        ]
        if active_peasants:
            names = ", ".join(a.name for a in active_peasants)
            error_console.print(f"[yellow]Warning:[/yellow] active peasant(s) on this ticket: {names}")
            error_console.print("Consider stopping them first with `kd peasant stop`.")
    except RuntimeError:
        pass  # no active branch — skip the check

    old_status = ticket.status
    closed_at = datetime.now(UTC).replace(microsecond=0)
    context = resolve_execution_context()
    ticket.status = "closed"
    ticket.closed_at = closed_at
    ticket.resolution = close_resolution
    ticket.close_reason = reason
    ticket.closed_context = context.context_id if context else None
    ticket.duplicate_of = duplicate_target_id if close_resolution == "duplicate" else None
    ticket.superseded_by = superseding_ticket_id if close_resolution == "superseded" else None
    reference_id = ticket.duplicate_of or ticket.superseded_by
    context_tag = f" [{ticket.closed_context}]" if ticket.closed_context else ""
    lifecycle_details = f"closed ({close_resolution})"
    if reference_id:
        lifecycle_details += f" [reference: {reference_id}]"
    if reason:
        lifecycle_details += f": {' '.join(reason.splitlines())}"
    lifecycle_timestamp = closed_at.isoformat().replace("+00:00", "Z")
    lifecycle_entry = f"- {lifecycle_timestamp}{context_tag} — {lifecycle_details}"
    ticket.body = insert_markdown_section_entry(ticket.body, "Lifecycle", lifecycle_entry).strip()
    write_ticket(ticket, ticket_path)
    clear_ticket_execution_contexts(base, ticket.id, now=closed_at)

    if reason:
        from kingdom.harness import format_worklog_timestamp

        append_worklog_entry(
            ticket_path,
            f"Closed: {reason}",
            timestamp=closed_at,
            timestamp_text=format_worklog_timestamp(closed_at),
            author=ticket.closed_context,
        )

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
    base = require_project_root()
    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    old_status = ticket.status
    reopened_at = datetime.now(UTC).replace(microsecond=0)

    if ticket.status == "closed":
        previous_resolution = effective_resolution(ticket) or "completed"
        reference_id = ticket.duplicate_of or ticket.superseded_by
        context = resolve_execution_context()
        context_tag = f" [{context.context_id}]" if context else ""
        lifecycle_details = f"reopened (previous: {previous_resolution})"
        if reference_id:
            lifecycle_details += f" [reference: {reference_id}]"
        if ticket.close_reason:
            lifecycle_details += f": {' '.join(ticket.close_reason.splitlines())}"
        lifecycle_timestamp = reopened_at.isoformat().replace("+00:00", "Z")
        lifecycle_entry = f"- {lifecycle_timestamp}{context_tag} — {lifecycle_details}"
        ticket.body = insert_markdown_section_entry(ticket.body, "Lifecycle", lifecycle_entry).strip()

    ticket.status = "open"
    ticket.closed_at = None
    ticket.resolution = None
    ticket.close_reason = None
    ticket.closed_context = None
    ticket.duplicate_of = None
    ticket.superseded_by = None
    write_ticket(ticket, ticket_path)

    archive_backlog_tickets = archive_root(base) / "backlog" / "tickets"
    if ticket_path.parent.resolve() == archive_backlog_tickets.resolve():
        ticket_path = move_ticket(ticket_path, backlog_root(base) / "tickets")

    clear_ticket_execution_contexts(base, ticket.id, now=reopened_at)
    typer.echo(f"{ticket.id}: {old_status} → open — {ticket.title}")


@ticket_app.command("status", help="Set a ticket's status to an arbitrary value.")
def ticket_status(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    status: Annotated[str, typer.Argument(help="New status (e.g. blocked, in_review, waiting).")],
) -> None:
    """Set ticket status to any arbitrary string."""
    ticket = update_ticket_status(ticket_id, status)
    if status != "in_progress":
        clear_ticket_execution_contexts(require_project_root(), ticket.id)


@ticket_app.command("delete", help="Permanently delete a ticket file.")
def ticket_delete(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt.")] = False,
) -> None:
    """Remove a ticket file from disk."""
    base = require_project_root()
    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)

    # Guard: refuse to delete if a peasant is actively working on this ticket
    branch_dir = ticket_path.parent.parent  # .kd/branches/<branch> or .kd/backlog
    if branch_dir.parent.name == "branches":
        from kingdom.session import get_agent_state

        branch_name = branch_dir.name
        session_name = peasant_session_name(ticket.id)
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
    clear_ticket_execution_contexts(base, ticket.id)
    typer.echo(f"Deleted {ticket.id} — {ticket.title}")


@deps_app.command("add", help="Add a dependency to a ticket.")
def deps_add(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    depends_on: Annotated[str, typer.Argument(help="ID of ticket this depends on.")],
) -> None:
    """Add a dependency: ticket_id depends on depends_on."""
    base = require_project_root()

    # Find both tickets
    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    dep_ticket, _ = resolve_ticket_or_exit(base, depends_on, not_found_label="Dependency ticket not found")

    # Add dependency if not already present
    if dep_ticket.id not in ticket.deps:
        ticket.deps.append(dep_ticket.id)
        write_ticket(ticket, ticket_path)
        typer.echo(f"{ticket.id}: now depends on {dep_ticket.id}")
    else:
        typer.echo(f"{ticket.id}: already depends on {dep_ticket.id}")


@deps_app.command("remove", help="Remove a dependency from a ticket.")
def deps_remove(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    depends_on: Annotated[str, typer.Argument(help="ID of dependency to remove.")],
) -> None:
    """Remove a dependency from a ticket."""
    base = require_project_root()

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)

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


@deps_app.command("tree", help="Show dependency tree for a ticket.")
def deps_tree(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    full: Annotated[bool, typer.Option("--full", help="Show duplicate subtrees instead of deduplicating.")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Display the dependency tree rooted at a ticket."""
    base = require_project_root()

    root_ticket, _ = resolve_ticket_or_exit(base, ticket_id)

    all_tickets = collect_all_tickets(base)
    ticket_map = {t.id: t for t in all_tickets}
    seen: set[str] = set()

    if output_json:

        def build_tree(tid: str, ancestors: frozenset[str] = frozenset()) -> dict:
            t = ticket_map.get(tid)
            node: dict = {
                "id": tid,
                "status": t.status if t else "unknown",
                "title": t.title if t else None,
            }
            if tid in ancestors:
                node["cycle"] = True
                return node
            if not full and tid in seen:
                node["duplicate"] = True
                return node
            seen.add(tid)
            if t and t.deps:
                child_ancestors = ancestors | {tid}
                node["deps"] = [build_tree(dep_id, child_ancestors) for dep_id in t.deps]
            return node

        typer.echo(json.dumps(build_tree(root_ticket.id), indent=2))
        return

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


@deps_app.command("cycle", help="Detect dependency cycles.")
def deps_cycle() -> None:
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
        result = resolve_ticket_or_exit(base, tid)
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

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    target, target_path = resolve_ticket_or_exit(base, target_id)

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

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    ticket.assignee = agent
    write_ticket(ticket, ticket_path)
    typer.echo(f"{ticket.id}: assigned to {agent}")


@ticket_app.command("unassign", help="Clear ticket assignment.")
def ticket_unassign(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Clear the assignee field on a ticket."""
    base = require_project_root()

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    ticket.assignee = None
    write_ticket(ticket, ticket_path)
    typer.echo(f"{ticket.id}: unassigned")


@ticket_app.command("parent", help="Set or clear the parent of a ticket.")
def ticket_parent(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    parent_id: Annotated[str | None, typer.Argument(help="Parent ticket ID to set.")] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Remove the parent.")] = False,
) -> None:
    """Set or clear a ticket's parent.

    Set parent:   kd tk parent <ticket-id> <epic-id>
    Clear parent: kd tk parent <ticket-id> --clear
    """
    if not parent_id and not clear:
        typer.echo("Provide a parent ticket ID or use --clear.", err=True)
        raise typer.Exit(1)
    if parent_id and clear:
        typer.echo("Cannot set a parent and --clear at the same time.", err=True)
        raise typer.Exit(1)

    base = require_project_root()
    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)

    if clear:
        old_parent = ticket.parent
        ticket.parent = None
        write_ticket(ticket, ticket_path)
        typer.echo(
            f"{ticket.id}: parent cleared (was {old_parent})" if old_parent else f"{ticket.id}: no parent to clear"
        )
    else:
        assert parent_id is not None
        parent_ticket, _ = resolve_ticket_or_exit(base, parent_id, not_found_label="Parent ticket not found")
        if parent_ticket.id == ticket.id:
            typer.echo("A ticket cannot be its own parent.", err=True)
            raise typer.Exit(1)
        old_parent = ticket.parent
        ticket.parent = parent_ticket.id
        write_ticket(ticket, ticket_path)
        if old_parent:
            typer.echo(f"{ticket.id}: parent {old_parent} → {parent_ticket.id}")
        else:
            typer.echo(f"{ticket.id}: parent set to {parent_ticket.id}")


@ticket_app.command("move", help="Move a ticket to another branch.")
def ticket_move(
    ticket_ids: Annotated[list[str], typer.Argument(help="Ticket ID(s) (full or partial).")],
    to_target: Annotated[str | None, typer.Option("--to", help="Target branch name or 'backlog'.")] = None,
) -> None:
    """Move ticket(s) to a different branch or backlog.

    Single ticket: `kd tk move <id> --to <branch>` or `kd tk move <id>` (to current branch).
    Multiple tickets: `kd tk move <id1> <id2> --to <branch>`.

    Searches all branches for the source ticket (IDs are globally unique).
    Validates --to target exists in .kd/branches/. Blocks moves on tickets
    with active peasant sessions.
    """
    from kingdom.session import find_active_peasant_branch

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
    elif target.lower() == "branch":
        # "branch" is a keyword meaning "current git branch"
        try:
            resolved = resolve_current_run(base)
        except RuntimeError:
            print_error("No current branch active. Use a branch name or run `kd start` first.")
            raise typer.Exit(code=1) from None
        dest_dir = branches_root(base) / normalize_branch_name(resolved) / "tickets"
        dest_label = f"branch '{resolved}'"
    else:
        normalized = normalize_branch_name(target)
        branch_dir = branches_root(base) / normalized
        # Validate target branch exists — no silent directory creation
        if not branch_dir.exists():
            print_error(f"Target branch '{target}' not found in .kd/branches/.")
            error_console.print("Use `kd start <branch>` to create it first.")
            raise typer.Exit(code=1)
        dest_dir = branch_dir / "tickets"
        dest_label = f"branch '{normalized}'"

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Pass 1: validate all tickets (search globally, not scoped to current branch)
    validated: list[tuple[Ticket, Path]] = []
    for tid in ticket_ids:
        ticket, ticket_path = resolve_ticket_or_exit(base, tid)
        if ticket_path.parent.resolve() == dest_dir.resolve():
            typer.echo(f"Ticket {ticket.id} is already in {dest_label}")
            continue

        # Block moves on tickets with active peasant sessions
        session_name = peasant_session_name(ticket.id)
        owning_branch = find_active_peasant_branch(base, session_name)
        if owning_branch:
            print_error(
                f"Ticket {ticket.id} has an active peasant session on branch '{owning_branch}'.\n"
                f"Stop the peasant first: `kd peasant stop {ticket.id}`"
            )
            raise typer.Exit(code=1)

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


@ticket_app.command("add-note", help="Append a timestamped note to a ticket.")
def ticket_add_note(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    text: Annotated[str | None, typer.Argument(help="Note text. Reads from stdin if omitted.")] = None,
) -> None:
    """Append a timestamped note to the ticket body."""
    base = require_project_root()

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)

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


@ticket_app.command("log", help="Append a worklog entry to a ticket.")
def ticket_log(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
    message: Annotated[str, typer.Argument(help="Worklog message to append.")],
) -> None:
    """Append a timestamped journal entry to the ticket's Worklog section."""
    from kingdom.ticket import append_worklog_entry

    base = require_project_root()

    ticket, ticket_path = resolve_ticket_or_exit(base, ticket_id)

    # Infer author from environment
    role = os.environ.get("KD_ROLE", "")
    agent_name = os.environ.get("KD_AGENT_NAME", "")
    author = agent_name or role or None
    if author is None:
        with contextlib.suppress(ValueError):
            context = resolve_execution_context()
            if context:
                author = compact_context_id(context.context_id)

    entry = append_worklog_entry(ticket_path, message, author=author)
    typer.echo(f"{ticket.id}: {entry}")


@ticket_app.command("edit", help="Open a ticket in $EDITOR.")
def ticket_edit(
    ticket_id: Annotated[str, typer.Argument(help="Ticket ID (full or partial).")],
) -> None:
    """Open a ticket file in the default editor."""
    base = require_project_root()

    _, ticket_path = resolve_ticket_or_exit(base, ticket_id)
    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([*shlex.split(editor), str(ticket_path)])

    # Post-edit validation: re-read and check type
    try:
        edited = read_ticket(ticket_path)
        if edited.type not in TICKET_TYPES:
            print_error(f"Invalid type '{edited.type}'. Valid types: {', '.join(sorted(TICKET_TYPES))}")
            raise typer.Exit(code=1)
    except (ValueError, FileNotFoundError):
        pass  # ticket was deleted or has broken frontmatter — not our problem here
