---
id: "ffc8"
status: closed
deps: [4b8b]
links: []
created: 2026-02-27T11:55:24Z
type: task
priority: 1
closed_at: 2026-02-27T19:40:04Z
---
# Split cli.py into domain modules (R2)

## Problem

`cli.py` is 4,960 lines with all 40+ commands, worktree management, council watch, peasant review, ticket rendering, and filtering tangled together. It should be a thin shell over the library layer.

## Scope

Mechanical split only — cut and paste functions into new modules without refactoring logic. Domain logic extraction is R3 (6a72), legacy `runs/` removal is R4 (bb0e).

## Acceptance Criteria

- [ ] `src/kingdom/cli.py` replaced by `src/kingdom/cli/` package
- [ ] `__init__.py`: root app, callback, top-level commands (start, done, doctor, status)
- [ ] `ticket.py`: all `kd tk` subcommands including `deps` sub-app
- [ ] `council.py`: all `kd council` subcommands (ask, show, list, status, watch, retry, review, reset, chat)
- [ ] `peasant.py`: all `kd peasant` subcommands
- [ ] `design.py`: `kd design` default prints design-doc path; `--show` renders full doc; `show`, `approve` subcommands
- [ ] `config.py`: `kd config` subcommands
- [ ] `display.py`: cross-cutting rendering only (`styled_echo`, `print_error`, `console_width`, `NO_COLOR`); domain-specific rendering stays with its module (ticket tables in `ticket.py`, thread status in `council.py`)
- [ ] `helpers.py`: `resolve_ticket_or_exit()` and shared CLI utilities
- [ ] Each module registers its own Typer sub-app; root `__init__.py` mounts them
- [ ] `kd --help` output looks correct
- [ ] All hidden aliases preserved (`tk`, `ticket ls`, `council ls`, etc.)
- [ ] `kingdom.cli:main` entry point unchanged — `__init__.py` re-exports `app` and `main`
- [ ] Test imports from `kingdom.cli` continue to resolve (re-export from `__init__` during transition)
- [ ] Legacy `runs/` fallback code moves with its host functions untouched — removal deferred to bb0e
- [ ] All tests pass with updated imports
