---
id: "b1de"
status: open
deps: []
links: []
created: 2026-08-19T21:46:02Z
type: epic
priority: 2
---
# Make Council reliable across sessions and repository states

Council operations should remain predictable when no workspace is active, when
agent backends are installed but unusable, when a review target is dirty, and
when chat messages arrive faster than a member can process them. Reliability and
recovery come before adding more Council backends or higher-level features.

## Acceptance Criteria

- [ ] Council list and ask commands handle missing active context without tracebacks or ambiguous fallback.
- [ ] Council review handles dirty repositories safely and gives an exact recovery path when it cannot proceed.
- [ ] Council chat queues messages without losing, overwriting, or silently reordering them.
- [ ] Doctor distinguishes an installed agent CLI from runtime, authentication, and configuration failures.
- [ ] Human errors and machine-readable behavior are covered by focused regressions and manual CLI checks.
- [ ] Every child ticket is closed with full-suite verification before the epic closes.

## Children

- `fe67` — list outside an active session
- `afd2` — ask outside an active session
- `478a` — review with uncommitted changes
- `953a` — queued chat messages
- `bd1f` — runtime and authentication diagnostics

## Scope Boundary

Backend additions, image input, and council-assisted ticket vetting remain
separate feature work. This epic is limited to failure handling, delivery
reliability, diagnostics, and recovery.
