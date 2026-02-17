---
id: "2def"
status: closed
deps: []
links: []
created: 2026-02-16T13:55:57Z
type: task
priority: 2
---
# Make 'kd tk create' print the created ticket file path

## Acceptance Criteria

- [x] `kd tk create` prints the file path on a second line after the "Created" message
- [x] Works for both branch and backlog tickets
- [x] Tests added: test_create_prints_file_path, test_create_backlog_prints_file_path
- [x] All existing tests still pass
- [x] Manual verification: output looks correct

## Work Log

- Added `typer.echo(str(ticket_path))` after the "Created" message in `ticket_create()`
- Added 2 new tests in `TestTicketCreate` class
- Fixed pre-existing test failures: removed stale cursor backend references from test_agent.py, test_council.py, test_tui_poll.py, test_init.py, test_done.py
- Fixed linter-broken f-strings in cli.py (Rich markup in `', '.join(...)` expressions)
