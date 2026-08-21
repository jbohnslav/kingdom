"""Host hook event handlers for Kingdom's ticket workflow.

The ``kd hook run`` subcommand reads a JSON payload from stdin, dispatches to
the appropriate handler after host normalization, and writes any response JSON
to stdout.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from kingdom.lifecycle import EventKind, Host, HostEvent, InvalidHostEvent, normalize_host_event
from kingdom.state import (
    ExecutionContext,
    archive_root,
    backlog_root,
    branch_root,
    compact_context_id,
    find_project_root,
    finish_execution_context,
    normalize_branch_name,
    read_execution_ticket_context,
    read_terminal_ticket_context,
    record_execution_ticket_context,
    resolve_current_run,
    resolve_execution_context,
    write_json,
)
from kingdom.ticket import (
    AmbiguousTicketMatch,
    append_worklog_entry,
    find_ticket,
    read_ticket,
    write_ticket,
)

hook_app = typer.Typer(name="hook", help="Agent-host hook handlers (internal).")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_START_BRIEF = (
    "KINGDOM WORKFLOW: You are working in a project managed by the kd CLI."
    " Before coding or research, ensure work is tracked with a ticket.\n"
    " 1. TICKET FIRST — King says something? Ask yourself: does this need a"
    " ticket? Bug, idea, complaint, scope change → kd tk create immediately.\n"
    " 2. LOG PROACTIVELY — Decision made, root cause found, scope changed,"
    " work completed → kd tk log. The King should never have to ask.\n"
    " 3. DEFER vs CREATE — Existing work is not for now → kd tk defer --reason."
    " New problem noticed → kd tk create --backlog."
)

USER_PROMPT_REMINDER = (
    "Kingdom: keep the ticket accurate (body/AC/status/worklog)."
    " Prefer the last ticket started in this terminal with `kd tk start` when logging."
    " Requirement or acceptance-criteria change -> edit ticket markdown now."
    " Work/findings -> kd tk log. Existing work not for now -> kd tk defer --reason."
    " New bug/scope -> kd tk create --backlog."
)

WORK_TOOLS = {"WebSearch", "WebFetch", "Edit", "Write", "apply_patch"}

STALE_TTL_SECONDS = 86400  # 24 hours
LEGACY_STOP_TICKET_FALLBACK_ENV = "KD_HOOK_LEGACY_TICKET_FALLBACK"

CHECKPOINT_FIELDS = "decisions, completed work, verification, blockers, and next steps"
CLAUDE_ENV_FILE_ENV = "CLAUDE_ENV_FILE"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def runtime_dir(project_dir: str | None = None) -> Path:
    """Return the .kd/runtime directory, creating it if needed."""
    base = Path(project_dir) if project_dir else Path(".")
    d = base / ".kd" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_file_for(project_dir: str | None, session_id: str, host: str = "claude") -> Path:
    """Return the turn-state file path for a given session."""
    identity = f"{host}\0{session_id}".encode()
    digest = hashlib.sha256(identity).hexdigest()[:16]
    return runtime_dir(project_dir) / f"turn-{host}-{digest}.json"


def checkpoint_state_file(base: Path, host: str, session_id: str) -> Path:
    identity = f"{host}\0{session_id}".encode()
    digest = hashlib.sha256(identity).hexdigest()[:16]
    return base / ".kd" / "runtime" / f"checkpoint-{digest}.json"


def read_turn_state(path: Path) -> dict | None:
    """Read turn state, returning None on any error (fail-open)."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_turn_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state))


def fresh_turn_state() -> dict[str, bool]:
    return {"had_work": False, "did_log": False, "stop_blocked": False}


def read_checkpoint(base: Path, event: HostEvent) -> dict | None:
    return read_turn_state(checkpoint_state_file(base, event.host.value, event.session_id))


def checkpoint_context(event: HostEvent) -> tuple[Path, ExecutionContext, dict] | None:
    base = terminal_context_base(str(event.cwd))
    context = resolve_execution_context(
        session_id=event.session_id,
        host=event.host.value,
        cwd=event.cwd,
        prefer_session_id=True,
    )
    if context is None:
        return None
    binding = read_execution_ticket_context(base, context)
    if binding is None:
        return None
    feature = binding.get("feature")
    ticket_id = binding.get("ticket_id")
    if not isinstance(feature, str) or not isinstance(ticket_id, str):
        return None
    result = find_ticket(base, ticket_id, branch=feature)
    if result is None or result.ticket.status != "in_progress":
        return None
    binding = dict(binding)
    binding["ticket_path"] = str(result.path.resolve())
    return base, context, binding


def checkpoint_message(ticket_id: str, phase: str) -> str:
    return (
        f"KINGDOM CHECKPOINT ({phase}) for exact ticket {ticket_id}: update its Markdown now with "
        f"{CHECKPOINT_FIELDS}. Do not substitute another branch ticket."
    )


def request_checkpoint(event: HostEvent, phase: str) -> tuple[dict, bool] | None:
    resolved = checkpoint_context(event)
    if resolved is None:
        return None
    base, context, binding = resolved
    path = checkpoint_state_file(base, event.host.value, event.session_id)
    current = read_turn_state(path)
    if current and current.get("ticket_id") == binding["ticket_id"]:
        return current, False

    checkpoint = {
        "schema_version": 1,
        "context_id": context.context_id,
        "host": event.host.value,
        "session_id": event.session_id,
        "ticket_id": binding["ticket_id"],
        "ticket_path": binding["ticket_path"],
        "phase": phase,
        "requested_at": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, checkpoint)
    return checkpoint, True


def logged_ticket_ids(command: str) -> set[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();&|\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return set()

    ticket_ids = set()
    command_tokens: list[str] = []
    commands: list[list[str]] = []
    for token in tokens:
        if token and all(character in "();&|\n" for character in token):
            if command_tokens:
                commands.append(command_tokens)
                command_tokens = []
            continue
        command_tokens.append(token)
    if command_tokens:
        commands.append(command_tokens)

    assignment = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
    for shell_command in commands:
        index = 0
        while index < len(shell_command) and assignment.match(shell_command[index]):
            index += 1
        if index < len(shell_command) and Path(shell_command[index]).name == "env":
            index += 1
            while index < len(shell_command) and assignment.match(shell_command[index]):
                index += 1
        if shell_command[index : index + 2] == ["uv", "run"]:
            index += 2
        if index >= len(shell_command) or Path(shell_command[index]).name != "kd":
            continue
        route = shell_command[index + 1 : index + 3]
        if route not in (["tk", "log"], ["ticket", "log"]):
            continue
        if index + 3 < len(shell_command):
            ticket_ids.add(shell_command[index + 3])
    return ticket_ids


def checkpoint_completed_by_event(base: Path, event: HostEvent, checkpoint: dict) -> bool:
    ticket_path = checkpoint.get("ticket_path")
    if isinstance(ticket_path, str):
        for file_path in event.file_paths:
            candidate = Path(file_path)
            if not candidate.is_absolute():
                candidate = event.cwd / candidate
            if candidate.resolve(strict=False) == Path(ticket_path):
                return True

    if event.tool_name not in {"Bash", "Shell"} or not event.command:
        return False
    ticket_id = checkpoint.get("ticket_id")
    return isinstance(ticket_id, str) and ticket_id in logged_ticket_ids(event.command)


def is_ticket_markdown_path(file_path: str, project_dir: str | None) -> bool:
    path = Path(file_path)
    if not path.is_absolute():
        base = Path(project_dir) if project_dir else Path(".")
        path = base / path

    path = path.resolve(strict=False)
    return path.suffix == ".md" and path.parent.name == "tickets" and ".kd" in path.parts


def is_ticket_markdown_event(event: HostEvent) -> bool:
    project_dir = str(event.cwd)
    return any(is_ticket_markdown_path(file_path, project_dir) for file_path in event.file_paths)


def ticket_paths_for_terminal_context(base: Path, ticket_id: str, feature: str, location: str | None) -> list[Path]:
    if location == "backlog":
        tickets_dir = backlog_root(base) / "tickets"
    elif location and location.startswith("archive:"):
        tickets_dir = archive_root(base) / location.removeprefix("archive:") / "tickets"
    elif location and location.startswith("branch:"):
        tickets_dir = branch_root(base, location.removeprefix("branch:")) / "tickets"
    else:
        tickets_dir = branch_root(base, feature) / "tickets"

    return [tickets_dir / f"{ticket_id}.md", tickets_dir / f"kin-{ticket_id}.md"]


def terminal_context_ticket_is_current(base: Path, ticket_id: str, feature: str, location: str | None = None) -> bool:
    candidate_paths = ticket_paths_for_terminal_context(base, ticket_id, feature, location)
    for ticket_path in candidate_paths:
        try:
            ticket = read_ticket(ticket_path)
        except (FileNotFoundError, ValueError, OSError):
            continue
        return (
            ticket.id == ticket_id
            and ticket.status == "in_progress"
            and not (ticket.assignee or "").startswith("peasant-")
        )
    return False


def terminal_context_base(project_dir: str | None) -> Path:
    fallback = Path(project_dir) if project_dir else Path(".")
    try:
        return find_project_root(fallback)
    except ValueError:
        return fallback


def find_stop_ticket_id(project_dir: str | None, session_id: str, host: str = "claude") -> str | None:
    base = terminal_context_base(project_dir)
    context = resolve_execution_context(session_id=session_id, host=host, cwd=Path(project_dir or "."))
    if context is not None:
        binding = read_execution_ticket_context(base, context)
        if binding:
            try:
                current_feature = normalize_branch_name(resolve_current_run(base))
            except (RuntimeError, ValueError):
                current_feature = None
            feature = binding.get("feature")
            ticket_id = binding.get("ticket_id")
            if current_feature and feature == current_feature and isinstance(ticket_id, str):
                result = find_ticket(base, ticket_id, branch=feature)
                if result and result.ticket.status == "in_progress" and result.ticket.assignee == context.context_id:
                    return ticket_id

    terminal_context = read_terminal_ticket_context(base, session_id=session_id)
    if terminal_context:
        try:
            current_feature = normalize_branch_name(resolve_current_run(base))
        except (RuntimeError, ValueError):
            current_feature = None
        ticket_id = terminal_context["ticket_id"]
        if (
            current_feature
            and terminal_context.get("feature") == current_feature
            and terminal_context_ticket_is_current(
                base,
                ticket_id,
                current_feature,
                terminal_context.get("location"),
            )
        ):
            return ticket_id

    if os.environ.get(LEGACY_STOP_TICKET_FALLBACK_ENV) != "1":
        return None

    try:
        proc = subprocess.run(
            ["kd", "tk", "current", "--id", "--exclude-peasant"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ticket_id = proc.stdout.strip()
        if proc.returncode != 0 or not ticket_id:
            return None
        return ticket_id
    except Exception:
        return None


def subagent_contexts(event: HostEvent) -> tuple[ExecutionContext | None, ExecutionContext | None]:
    if not event.agent_id or not event.parent_agent_id:
        return None, None
    parent = resolve_execution_context(
        session_id=event.parent_agent_id,
        host=event.host.value,
        cwd=event.cwd,
    )
    if parent is None:
        return None, None
    child = resolve_execution_context(
        session_id=event.agent_id,
        host=event.host.value,
        role="subagent",
        parent_agent_id=parent.context_id,
        agent_type=event.agent_type,
        cwd=event.cwd,
    )
    return parent, child


def subagent_context_output(event: HostEvent, message: str) -> str:
    if event.host is Host.CURSOR:
        # Cursor's stable schema can allow or deny creation, but cannot inject
        # context into an allowed subagent. Record the binding and fail open.
        return json.dumps({"permission": "allow"})
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": message,
            }
        }
    )


def assign_explicit_subagent_ticket(
    base: Path,
    feature: str,
    event: HostEvent,
    child: ExecutionContext,
) -> str | None:
    if not event.ticket_hint:
        return None
    try:
        result = find_ticket(base, event.ticket_hint, branch=feature)
    except AmbiguousTicketMatch:
        return f"Kingdom could not resolve explicit ticket {event.ticket_hint}; run kd tk start <id>."
    if result is None:
        return f"Kingdom could not find explicit ticket {event.ticket_hint}; run kd tk start <id>."

    ticket = result.ticket
    if ticket.status not in {"open", "in_progress"}:
        return f"Kingdom ticket {ticket.id} is {ticket.status}; run kd tk start <id> for another ticket."
    if ticket.assignee and ticket.assignee != child.context_id:
        return f"Kingdom ticket {ticket.id} already has an owner; run kd tk start <id> explicitly if reassignment is intended."

    ticket.status = "in_progress"
    ticket.assignee = child.context_id
    write_ticket(ticket, result.path)
    record_execution_ticket_context(
        base,
        child,
        ticket.id,
        feature=feature,
        location=result.location,
    )
    return (
        f"Kingdom assigned you ticket {ticket.id}. Keep its Markdown body, acceptance criteria, and worklog current; "
        "do not close it unless your parent asked you to own completion."
    )


# ---------------------------------------------------------------------------
# Event handlers — each consumes normalized events and returns hook output.
# ---------------------------------------------------------------------------


def handler_event(data: HostEvent | dict, expected: EventKind) -> HostEvent | None:
    """Normalize direct legacy handler calls; the CLI normalizes before dispatch."""
    if isinstance(data, HostEvent):
        return data if data.kind is expected else None
    if not data.get("hook_event_name"):
        return None
    try:
        event = normalize_host_event(detect_hook_host(data), data)
    except InvalidHostEvent:
        return None
    return event if event and event.kind is expected else None


def persist_claude_session_environment(event: HostEvent) -> str | None:
    env_path = os.environ.get(CLAUDE_ENV_FILE_ENV)
    if event.host is not Host.CLAUDE or not env_path:
        return None

    try:
        with Path(env_path).open("a", encoding="utf-8") as env_file:
            env_file.write(f"export KD_CONTEXT={shlex.quote(event.session_id)}\n")
            env_file.write(f"export KD_HOST={shlex.quote(event.host.value)}\n")
    except OSError as exc:
        return f"Kingdom could not persist the Claude session identity: {exc}"
    return None


def reactivate_resumed_context(base: Path, event: HostEvent) -> None:
    context = resolve_execution_context(
        session_id=event.session_id,
        host=event.host.value,
        cwd=event.cwd,
        prefer_session_id=True,
    )
    if context is None:
        return
    binding = read_execution_ticket_context(base, context)
    if binding is None or binding.get("active") is not False:
        return
    feature = binding.get("feature")
    ticket_id = binding.get("ticket_id")
    if not isinstance(feature, str) or not isinstance(ticket_id, str):
        return
    result = find_ticket(base, ticket_id, branch=feature)
    if result is None or result.ticket.status != "in_progress" or result.ticket.assignee != context.context_id:
        return
    location = binding.get("location")
    record_execution_ticket_context(
        base,
        context,
        ticket_id,
        feature=feature,
        location=location if isinstance(location, str) else None,
    )


def handle_session_start(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.SESSION_START)
    if event is None:
        return ""
    additional_context = SESSION_START_BRIEF
    environment_warning = persist_claude_session_environment(event)
    if environment_warning:
        additional_context += "\n\n" + environment_warning
    base = terminal_context_base(str(event.cwd))
    reactivate_resumed_context(base, event)
    checkpoint = read_checkpoint(base, event)
    if checkpoint and event.source == "compact":
        additional_context += "\n\n" + checkpoint_message(checkpoint["ticket_id"], "compact resume")
    if event.host is Host.CURSOR:
        return json.dumps(
            {
                "env": {"KD_CONTEXT": event.session_id, "KD_HOST": event.host.value},
                "additional_context": additional_context,
            }
        )
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": additional_context,
            }
        }
    )


def handle_pre_compact(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.PRE_COMPACT)
    if event is None:
        return ""
    requested = request_checkpoint(event, "before compaction")
    if requested is None:
        return ""
    checkpoint, created = requested
    if not created:
        return ""
    message = checkpoint_message(checkpoint["ticket_id"], "before compaction")
    if event.host is Host.CURSOR:
        return json.dumps({"user_message": message})
    return json.dumps({"systemMessage": message})


def handle_post_compact(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.POST_COMPACT)
    if event is None:
        return ""
    base = terminal_context_base(str(event.cwd))
    checkpoint = read_checkpoint(base, event)
    if checkpoint is None:
        return ""
    return json.dumps({"systemMessage": checkpoint_message(checkpoint["ticket_id"], "after compaction")})


def handle_session_end(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.SESSION_END)
    if event is None:
        return ""
    requested = request_checkpoint(event, "session handoff")
    base = terminal_context_base(str(event.cwd))
    context = resolve_execution_context(
        session_id=event.session_id,
        host=event.host.value,
        cwd=event.cwd,
        prefer_session_id=True,
    )
    if context is not None:
        finish_execution_context(base, context)
    if requested is None:
        return ""
    checkpoint, _ = requested
    if event.host is Host.CURSOR:
        # Cursor documents sessionEnd responses as fire-and-forget. Preserve
        # checkpoint state for recovery without claiming the message is shown.
        return ""
    return json.dumps({"systemMessage": checkpoint_message(checkpoint["ticket_id"], "session handoff")})


def handle_subagent_start(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.SUBAGENT_START)
    if event is None:
        return ""
    parent, child = subagent_contexts(event)
    if parent is None or child is None:
        return subagent_context_output(
            event, "Kingdom could not identify this subagent context; run kd tk start <id> explicitly."
        )

    base = terminal_context_base(str(event.cwd))
    try:
        feature = resolve_current_run(base)
    except (RuntimeError, ValueError):
        return subagent_context_output(
            event,
            "Kingdom has no active feature here; run kd start before binding a ticket.",
        )

    explicit_message = assign_explicit_subagent_ticket(base, feature, event, child)
    if explicit_message:
        return subagent_context_output(event, explicit_message)

    parent_binding = read_execution_ticket_context(base, parent)
    if parent_binding is None or parent_binding.get("feature") != normalize_branch_name(feature):
        return subagent_context_output(
            event, "Kingdom found no exact parent ticket to inherit; run kd tk start <id> explicitly."
        )

    ticket_id = parent_binding["ticket_id"]
    record_execution_ticket_context(
        base,
        child,
        ticket_id,
        feature=feature,
        location=parent_binding.get("location"),
    )
    return subagent_context_output(
        event,
        f"Kingdom: inherit Kingdom ticket {ticket_id} from {compact_context_id(parent.context_id)}. "
        "Keep its Markdown body, acceptance criteria, and worklog current; leave closure to the owning session.",
    )


def handle_subagent_stop(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.SUBAGENT_STOP)
    if event is None:
        return ""
    parent, child = subagent_contexts(event)
    if parent is None or child is None:
        return ""

    base = terminal_context_base(str(event.cwd))
    binding = read_execution_ticket_context(base, child)
    if binding:
        feature = binding.get("feature")
        ticket_id = binding.get("ticket_id")
        if isinstance(feature, str) and isinstance(ticket_id, str):
            result = find_ticket(base, ticket_id, branch=feature)
            if result:
                agent_type = child.agent_type or "worker"
                append_worklog_entry(
                    result.path,
                    (
                        f"Native subagent {agent_type} completed; handoff returned to owning session "
                        f"{compact_context_id(parent.context_id)}."
                    ),
                    author=compact_context_id(child.context_id),
                )
    finish_execution_context(base, child)
    return ""


def handle_user_prompt_submit(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.PROMPT_SUBMIT)
    if event is None:
        return ""
    project_dir = str(event.cwd)
    session_id = event.session_id

    sf = state_file_for(project_dir, session_id, event.host.value)
    write_turn_state(sf, fresh_turn_state())

    # TTL cleanup: remove stale turn-state files.
    cutoff = time.time() - STALE_TTL_SECONDS
    rd = runtime_dir(project_dir)
    for f in rd.glob("turn-*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass

    if event.host is Host.CURSOR:
        # Cursor only shows user_message when a prompt is blocked. Kingdom does
        # not block merely to inject a reminder.
        return json.dumps({"continue": True})
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": USER_PROMPT_REMINDER,
            }
        }
    )


def handle_post_tool_use(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.POST_TOOL_USE)
    if event is None:
        return ""
    project_dir = str(event.cwd)
    session_id = event.session_id

    base = terminal_context_base(project_dir)
    checkpoint_path = checkpoint_state_file(base, event.host.value, event.session_id)
    checkpoint = read_turn_state(checkpoint_path)
    if checkpoint and checkpoint_completed_by_event(base, event, checkpoint):
        checkpoint_path.unlink(missing_ok=True)

    sf = state_file_for(project_dir, session_id, event.host.value)
    state = read_turn_state(sf)
    if state is None:
        return ""

    tool = event.tool_name or ""
    ticket_markdown_edit = is_ticket_markdown_event(event)

    if tool in WORK_TOOLS and not ticket_markdown_edit:
        state["had_work"] = True

    if ticket_markdown_edit:
        state["did_log"] = True

    if tool in {"Bash", "Shell"} and event.command and logged_ticket_ids(event.command):
        state["did_log"] = True

    write_turn_state(sf, state)
    return ""


def handle_stop(data: HostEvent | dict) -> str:
    event = handler_event(data, EventKind.STOP)
    if event is None:
        return ""
    # If stop_hook_active is set, another stop handler is running — bail.
    if event.stop_hook_active:
        return ""

    project_dir = str(event.cwd)
    session_id = event.session_id

    sf = state_file_for(project_dir, session_id, event.host.value)
    state = read_turn_state(sf)
    if state is None:
        return ""

    if state.get("stop_blocked"):
        return ""

    if not (state.get("had_work") and not state.get("did_log")):
        return ""

    # Check for an active ticket (fail-open on any error).
    ticket_id = find_stop_ticket_id(project_dir, session_id, event.host.value)
    if not ticket_id:
        return ""  # Timeout or error — fail open.

    reason = (
        f"KINGDOM: You did meaningful work this turn but didn't log it."
        f" Run: kd tk log {ticket_id} 'summary of what you did'"
    )
    if event.host is Host.CURSOR:
        result = {"followup_message": reason}
    else:
        result = {"decision": "block", "reason": reason}
    state["stop_blocked"] = True
    write_turn_state(sf, state)
    return json.dumps(result)


# Map event names to handlers.
HANDLERS = {
    EventKind.SESSION_START: handle_session_start,
    EventKind.SESSION_END: handle_session_end,
    EventKind.PRE_COMPACT: handle_pre_compact,
    EventKind.POST_COMPACT: handle_post_compact,
    EventKind.SUBAGENT_START: handle_subagent_start,
    EventKind.SUBAGENT_STOP: handle_subagent_stop,
    EventKind.PROMPT_SUBMIT: handle_user_prompt_submit,
    EventKind.POST_TOOL_USE: handle_post_tool_use,
    EventKind.STOP: handle_stop,
}


def detect_hook_host(data: dict) -> Host:
    event_name = data.get("hook_event_name")
    if isinstance(event_name, str) and event_name[:1].islower():
        return Host.CURSOR
    if os.environ.get("CURSOR_PROJECT_DIR"):
        return Host.CURSOR
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return Host.CLAUDE
    if os.environ.get("CODEX_THREAD_ID"):
        return Host.CODEX
    return Host.CLAUDE


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@hook_app.command("run", help="Process an agent-host hook event from stdin.")
def hook_run(
    host: Annotated[Host | None, typer.Option("--host", help="Source host; inferred when omitted.")] = None,
) -> None:
    """Read hook payload JSON from stdin, dispatch by event, write response."""
    # Bypass all processing if requested.
    if os.environ.get("KD_HOOK_BYPASS") == "1":
        return

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return  # Fail open on bad input.
    if not data or not data.get("hook_event_name"):
        return

    resolved_host = host or detect_hook_host(data)
    try:
        event = normalize_host_event(resolved_host, data)
    except InvalidHostEvent as exc:
        typer.echo(f"Kingdom hook diagnostic ({resolved_host}): {exc}", err=True)
        return
    if event is None:
        return  # Unknown event — silent.

    handler = HANDLERS.get(event.kind)
    if handler is None:
        return
    try:
        output = handler(event)
    except Exception as exc:
        typer.echo(f"Kingdom hook diagnostic ({resolved_host} {event.kind}): {exc}", err=True)
        return

    if output:
        typer.echo(output)
