# Design: ticket-management-ux

## Goal

Improve the ticket lifecycle CLI so that creating, moving, and closing tickets
is frictionless for both humans and agents.

## Context

Three pain points today:

1. **`kd tk create` only prints the ticket ID** — callers need the file path to
   edit the ticket body afterward. Currently requires a second lookup step.

2. **Closing a backlog ticket leaves it in place** — closed backlog tickets
   still appear in listings. They should move to archive automatically.

3. **No way to batch-pull backlog tickets** — `kd tk move` exists but targets
   arbitrary branches. A dedicated `kd tk pull` command makes the common
   "grab tickets from backlog into my branch" workflow explicit.

## Requirements

### kin-7402: Simplify ticket create
- `kd tk create "title"` creates ticket, prints the **absolute file path**
- Caller can then edit the file directly: `vim $(kd tk create "Fix bug")`
- Keep existing `-d`, `-p`, `-t`, `--backlog` flags for scripting
- Priority clamping warning goes to stderr (not stdout) to avoid breaking pipes

### kin-613d: Auto-archive closed backlog tickets
- When `kd tk close` is called on a backlog ticket, move it to
  `.kd/archive/backlog/tickets/`
- When `kd tk reopen` is called on an archived backlog ticket, move it back
  to `.kd/backlog/tickets/`
- Branch tickets stay in their branch (already correct behavior)
- Detection: compare `ticket_path.parent` against `backlog_root(base) / "tickets"`
  using resolved paths (not string matching)
- `update_ticket_status` is the choke point — add the move logic there

### kin-341e: `kd tk pull` command
- `kd tk pull <id> [<id>...]` moves tickets from backlog to current branch
- Requires an active run (`resolve_current_run`); errors explicitly if none
- Uses `move_ticket()` under the hood (plain rename, not git mv)
- Validates each ticket is in backlog before moving; fail-fast on first error
- Prints the new path for each moved ticket
- No `--all` flag — explicit IDs only, scriptable via `kd tk list --backlog`

## Non-Goals
- Changing ticket ID format (separate ticket kin-98e7)
- Auto-pull on `kd work` (separate ticket kin-d5ae)
- Git-tracked moves (`git mv`) — tickets in `.kd/` use plain rename today
- `--all` flag on pull (YAGNI; scriptable with `kd tk list --backlog | xargs`)

## Decisions

Council reviewed (thread council-63a2). Unanimous on all points:

- **Absolute path on stdout** for create — robust for piping into `$EDITOR`
- **Archive location**: `.kd/archive/backlog/tickets/` mirrors source structure
- **Reopen restores to backlog** — if auto-archive on close, auto-restore on
  reopen. Otherwise reopened tickets are invisible to `kd tk list --backlog`
- **`kd tk pull` is a separate command** (not a flag on move): semantics are
  different — pull is always backlog→current branch, move is arbitrary
- **No `--all`**: backlog is a triage buffer, pulling everything defeats the
  purpose. Explicit IDs are a natural guardrail
- **Fail-fast on multi-ID pull**: validate before moving, stop on first error
