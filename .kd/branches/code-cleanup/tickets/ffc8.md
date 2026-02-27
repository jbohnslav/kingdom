---
id: "ffc8"
status: open
deps: [4b8b]
links: []
created: 2026-02-27T11:55:24Z
type: task
priority: 1
---
# Split cli.py into domain modules (R2)

## Problem

`cli.py` is 4,960 lines with all 40+ commands, worktree management, council watch, peasant review, ticket rendering, and filtering tangled together. It should be a thin shell over the library layer.

## Acceptance Criteria

- [ ] `cli.py` replaced by `kingdom/cli/` package
- [ ] `__init__.py`: root app, callback, top-level commands (start, done, doctor, status)
- [ ] `ticket.py`: all `kd tk` subcommands including `deps` sub-app
- [ ] `council.py`: all `kd council` subcommands (ask, show, list, status, watch, retry, review, reset, chat)
- [ ] `peasant.py`: all `kd peasant` subcommands
- [ ] `design.py`: `kd design` (path, show, approve)
- [ ] `config.py`: `kd config` subcommands
- [ ] `display.py`: shared rendering (ticket tables, panels, status formatting)
- [ ] `helpers.py`: `resolve_ticket_or_exit()` and shared CLI utilities
- [ ] Each module registers its own Typer sub-app; root `__init__.py` mounts them
- [ ] `kd --help` output looks correct
- [ ] All tests pass with updated imports
