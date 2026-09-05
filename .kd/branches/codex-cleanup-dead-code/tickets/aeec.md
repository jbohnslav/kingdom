---
id: "aeec"
status: open
links: []
created: 2026-09-05T21:30:56Z
type: task
priority: 2
deps: ["79a4"]
parent: "1465"
---
# Remove inert CLI options and design approval ceremony

Expand the existing force-option ticket to cover audit findings 10–11. Remove kd start --force/-f, which is accepted but ignored. Make ticket create -t consistently mean title; --type is the explicit type option. Remove design approve and its hidden accept alias, design_approved presentation, and instructions that require that ceremony. Retain plain design initialization/show and useful tk/ls shortcuts. Register council ls directly on the list implementation rather than maintaining a duplicate wrapper/signature.

The force option was originally observed in help during audit 6509; this expanded scope follows the King's request for all six cleanup areas.

## Acceptance Criteria

- [ ] kd start help exposes no inert force option; start remains idempotent.
- [ ] -t consistently means ticket title and --type selects type; legacy overloaded parsing is removed.
- [ ] Design approval command/alias/field presentation and associated workflow instructions are removed; design init/show still work.
- [ ] Useful aliases share their implementation without signature-copy wrappers.
- [ ] Manual help and CLI examples look correct; full suite including Textual integration passes.

## Worklog

- 2026-09-05 — Scoped from the King’s request for the full six-area cleanup; historical closed-ticket compatibility is not a preservation requirement. Reused and expanded the existing backlog ticket, moved onto the cleanup branch, to avoid duplicate work.
