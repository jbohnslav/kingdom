---
id: "aeec"
status: closed
deps: [79a4]
links: []
created: 2026-09-05T21:30:56Z
type: task
priority: 2
closed_at: 2026-09-06T00:03:36Z
resolution: completed
closed_context: codex:a65a16d552d2bd0a
assignee: codex:a65a16d552d2bd0a
parent: 1465
---
# Remove inert CLI options and design approval ceremony

Expand the existing force-option ticket to cover audit findings 10–11. Remove kd start --force/-f, which is accepted but ignored. Make ticket create -t consistently mean title; --type is the explicit type option. Remove design approve and its hidden accept alias, design_approved presentation, and instructions that require that ceremony. Retain plain design initialization/show and useful tk/ls shortcuts. Register council ls directly on the list implementation rather than maintaining a duplicate wrapper/signature.

The force option was originally observed in help during audit 6509; this expanded scope follows the King's request for all six cleanup areas.

## Acceptance Criteria

- [x] kd start help exposes no inert force option; start remains idempotent.
- [x] -t consistently means ticket title and --type selects type; legacy overloaded parsing is removed.
- [x] Design approval command/alias/field presentation and associated workflow instructions are removed; design init/show still work.
- [x] Useful aliases share their implementation without signature-copy wrappers.
- [x] Manual help and CLI examples look correct; full suite including Textual integration passes.

## Worklog

- 2026-09-05 — Scoped from the King’s request for the full six-area cleanup; historical closed-ticket compatibility is not a preservation requirement. Reused and expanded the existing backlog ticket, moved onto the cleanup branch, to avoid duplicate work.
- [2026-09-05 20:03] [codex:a65a16d5] — Removed inert start force option, design approval/accept command and field presentation, overloaded -t type parsing, and council ls signature wrapper. -t/--title now share one option, --type is explicit, and ls registers directly on list. Updated affected docs and CLI tests. Manually verified start/design/create help, isolated short-title bug creation, duplicate-title rejection, design initialization/show, and council ls JSON.
  Validation: uv run pytest --run-textual-integration: 2350 passed, 3 skipped, 1 xfailed (37.98s). Ruff check and format passed. Captured rendered design placeholder issue separately as backlog cdc4.

## Lifecycle

- 2026-09-06T00:03:36Z [codex:a65a16d552d2bd0a] — closed (completed)
