---
id: "0ddb"
status: closed
deps: []
links: []
created: 2026-08-02T13:58:06Z
type: task
priority: 2
closed_at: 2026-08-03T14:56:20Z
resolution: completed
close_reason: "Kept pull as byte-preserving backlog selection with optional isolated --start binding and conflict preflight"
closed_context: codex:c4c6c1e74805c884
assignee: hand
parent: 48dd
---
# Keep tk pull as the canonical backlog-to-work flow

Preserve the useful one-way action that selects backlog work for the active branch
or workspace. Pull is not the same thing as generic movement.

## Acceptance Criteria

- [x] `tk pull` keeps the ticket ID, Markdown, links, dependencies, and parent/epic relationship.
- [x] Pull can optionally start/bind the ticket for the calling context without affecting other sessions.
- [x] Pulling an already-active ticket is idempotent or gives a precise conflict.
- [x] Help describes pull as backlog-to-work selection.
- [x] Manual output is checked for a backlog sprint and an epic child.

## Worklog

- 2026-08-03 — Added contract tests before implementation for byte-identical
  Markdown plus links/dependencies/parent preservation, optional single-ticket
  `pull --start` binding, caller isolation, context and multi-ticket preflight,
  active ownership conflicts, destination conflicts, and help wording. Red run:
  `TestTicketPull` had 7 expected failures and 10 passes. The failures confirmed
  that `--start` did not exist, already-selected tickets were reported as missing,
  a late destination collision partially moved the first ticket, and help still
  described only a directory move.

- 2026-08-03 — Implemented a preflighted backlog-to-work selection path. Plain
  multi-ticket pull retains its output, while `--start` accepts exactly one open,
  unconflicted ticket, moves it, and binds only the caller. Focused verification:
  all 17 pull tests pass; the combined lifecycle/current-context suites pass with
  139 tests. Ruff check and format check pass.

- 2026-08-03 — Manual CLI checks in a fresh temporary repository exercised both
  workflows. Backlog sprint output was `Pulled and started 8b2e — Manual sprint
  task`, followed by `tk current --id` returning `8b2e`. An epic child with parent
  `6666`, dependency/link `8b2e`, and existing Markdown produced `Pulled b835 —
  Manual epic child`; its SHA-1 was identical before and after the move. `tk show`
  retained the parent, dependency, link, and body, repeat pull reported the exact
  active branch, and help presented pull as selection for work with `--start`.

- 2026-08-03 — Full verification passed: 2,065 tests passed, 38 skipped, and one
  expected failure in 21.07 seconds. Final Ruff check, format check, and diff check
  remained clean.

- 2026-08-03 — Parent review confirmed plain pull remains byte-preserving,
  `--start` mutates only the calling context after full preflight, and all batch
  conflicts fail before the first move. Independently reran the lifecycle/current
  suites (139 passed), Ruff check/format, diff check, and inspected the rendered
  `tk pull --help` before acceptance.
- [10:56] [codex:c4c6c1e74805c884] — Closed: Kept pull as byte-preserving backlog selection with optional isolated --start binding and conflict preflight

## Lifecycle

- 2026-08-03T14:56:20Z [codex:c4c6c1e74805c884] — closed (completed): Kept pull as byte-preserving backlog selection with optional isolated --start binding and conflict preflight
