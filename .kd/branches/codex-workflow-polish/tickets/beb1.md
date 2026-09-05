---
id: "beb1"
status: closed
deps: []
links: []
created: 2026-08-02T14:08:00Z
type: task
priority: 2
closed_at: 2026-08-03T15:37:42Z
resolution: completed
closed_context: codex:a775e0448cdb5a76
assignee: codex:2b774495e85ef049
parent: 329d
---
# Fix tk list --parent table rendering and hierarchy context

Dogfooding `kd tk list --parent c759` with six children produced a malformed Rich
table: doubled border columns, the title column disappeared, and the location text
was truncated beyond usefulness. Parent-filtered output is central to epic work and
should prioritize child identity/title/dependency state over redundant location.

## Acceptance Criteria

- [x] `kd tk list --parent ID` renders valid borders at narrow, normal, and wide terminal widths.
- [x] ID, status, title, and blocking dependencies remain visible in the default parent view.
- [x] Redundant location is hidden or compacted when all rows share the current branch.
- [x] Long titles/dependency lists wrap or truncate intentionally with no missing header.
- [x] A regression test covers the observed six-child output shape.
- [x] Human and JSON output continue to agree on the selected children.

## Worklog

- 2026-08-03 — Reproduced the dogfood failure with `uv run kd tk list
  --parent c759`: `ID`, priority, and `Title` collapsed to zero-width columns,
  dependency text was truncated, and the shared `branch:codex-workflow-polish`
  location consumed a column on every row. JSON output still selected the same
  seven children correctly.

- 2026-08-03 — Root cause: `render_ticket_table()` forces a minimum 120-column
  console, lets the non-wrapping dependency column consume the flexible width,
  and `--parent` inherits the `--all` location column even when every child has
  the same location. Hiding location by itself is insufficient; the title still
  collapses beside a long dependency list.

- 2026-08-03 — Added a regression test based on the observed six-child shape.
  It checks 60/120/180-column human output for visible hierarchy fields,
  complete dependency context, bounded valid borders, hidden redundant location,
  and agreement with JSON-selected child IDs. Confirmed it fails before the fix:
  `uv run pytest -q tests/test_cli_ticket_list.py -k
  parent_table_preserves_six_child_hierarchy` fails because `ID` disappears.

- 2026-08-03 — Fixed rendering directly in `render_ticket_table()`: honor the
  detected terminal width, give `Title` and `Deps` proportional flexible space,
  allow dependency lists to wrap, and cap overflowing locations. Parent-filtered
  output now omits `Location` when every selected child shares one location, but
  keeps it when location distinguishes the rows.

- 2026-08-03 — Verification complete for handoff. The regression passes at
  simulated 60/120/180-column widths; `uv run pytest -q
  tests/test_cli_ticket_list.py` passes all 79 tests; `uv run ruff check
  src/kingdom/cli/ticket.py tests/test_cli_ticket_list.py` and `git diff
  --check` pass. Manual `uv run kd tk list --parent c759` inspection showed valid
  borders, visible ID/priority/status/title/deps, wrapped long rows, all seven
  current children, and no redundant location. `uv run kd tk list --parent c759
  --json` returned those same seven child IDs with full dependency data.

## Lifecycle

- 2026-08-03T15:37:42Z [codex:a775e0448cdb5a76] — closed (completed)
