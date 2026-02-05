---
id: kin-ce7d
status: closed
deps: [kin-aa3d]
links: []
created: 2026-02-04T21:23:13Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Add ticket CLI - core CRUD

Add kd ticket subcommand group: create, list, show commands with --backlog, --all, partial ID matching.

## Acceptance Criteria

- [x] kd ticket create works with all options
- [x] kd ticket list shows current branch tickets
- [x] kd ticket list --all shows all tickets with location
- [x] kd ticket show displays full ticket
- [x] Partial ID matching works

## Work Log

### 2026-02-04
- Added `ticket_app` typer subcommand group to `cli.py`
- Added imports for ticket module functions (find_ticket, list_tickets, etc.)
- Implemented `kd ticket create` with options:
  - `-d/--description`: Ticket description
  - `-p/--priority`: Priority level (1-3)
  - `-t/--type`: Ticket type (task, bug, feature)
  - `--backlog`: Create in backlog instead of current branch
- Implemented `kd ticket list` with options:
  - `--all/-a`: List all tickets across all locations with location labels
  - `--json`: Output as JSON
- Implemented `kd ticket show` with:
  - Partial ID matching via find_ticket()
  - `--json`: Output structured JSON
  - Human-readable markdown rendering via Rich
- Added `_get_tickets_dir()` helper to resolve tickets directory based on context
- All 146 tests passing
- Note: Existing `.tickets/` directory tickets will be migrated in kin-4a5e

