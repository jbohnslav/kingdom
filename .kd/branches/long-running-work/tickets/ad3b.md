---
id: "ad3b"
status: closed
deps: []
links: []
created: 2026-03-05T16:30:00Z
type: task
priority: 2
closed_at: 2026-03-06T01:51:05Z
---
# Add kd tk status command for setting arbitrary ticket status

## Description

Currently ticket status can only be set via dedicated commands (`kd tk start` → in_progress, `kd tk close` → closed, `kd tk reopen` → open). There's no way to set an arbitrary status like `blocked`, `in_review`, etc. The `update_ticket_status()` helper already supports any string — just need a CLI command exposing it.

## Acceptance Criteria

- [ ] `kd tk status <id> <status>` sets the ticket's status to the given string
- [ ] Output matches existing pattern: `id: old → new — title`
- [ ] `kd tk status --help` works
- [ ] Test covering the new command

## Worklog

- 2026-03-05 11:30 — Splitting into two tickets per King's direction
- 2026-03-05 20:51 — Implemented kd tk status <id> <status> command. Uses existing update_ticket_status() helper. Added two tests (set arbitrary value + round trip). Full suite green (1668 passed).
