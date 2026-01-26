---
id: kin-d0b5
status: closed
deps: [kin-ac22]
links: []
created: 2026-01-25T22:52:58Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd, state]
---
# .kd run state layout + helpers

Implement MVP .kd/ layout (.kd/config.json, .kd/current, .kd/runs/<feature>/{state.json,plan.md,logs/*}). Add helpers for mkdirp, JSON read/write, and resolving current run.

## Acceptance Criteria

kd start creates expected .kd paths; commands that require a run fail clearly when no current run.

