---
id: kin-341e
status: closed
deps: []
links: []
created: 2026-02-13T14:28:29Z
type: task
priority: 2
---
# Add kd tk pull command to move backlog tickets to current branch

Separate from the auto-pull on `kd work` (kin-d5ae), we need an explicit `kd tk pull` command for batch-moving backlog tickets into the current branch. Use case: you're on a misc/cleanup branch, you see a bunch of relevant backlog tickets, and you want to pull them all in at once so they show up in `kd tk list` and `kd tk ready`.

## Acceptance Criteria

- [x] `kd tk pull <ticket-id>` moves a single ticket from backlog to current branch
- [x] `kd tk pull <id1> <id2> <id3>` supports multiple ticket IDs in one call
- [x] Uses `move_ticket()` (plain rename, consistent with all other ticket moves — `git mv` dropped per design review)
- [x] Ticket appears in `kd tk list` / `kd tk ready` after pull
- [x] Error if ticket isn't in the backlog
- [x] Two-pass validation: all tickets validated before any are moved
- [x] Duplicate IDs in one call are deduplicated
