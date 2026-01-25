---
id: kin-43a7
status: open
deps: [kin-d0b5, kin-2cbb, kin-c6d0, kin-f968]
links: []
created: 2026-01-25T22:53:29Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd, git, tmux]
---
# kd peasant <ticket> (single worktree + tmux window)

Implement kd peasant <ticket>: create git worktree for ticket (MVP: peasant-1 only), create peasant-1 tmux window and start agent CLI in that worktree, record assignment in .kd/runs/<feature>/state.json.

## Acceptance Criteria

kd peasant <ticket-id> creates worktree and starts peasant-1 in correct cwd; state records assigned ticket.

