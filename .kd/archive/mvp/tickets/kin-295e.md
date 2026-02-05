---
id: kin-295e
status: closed
deps: [kin-2cbb, kin-c6d0]
links: []
created: 2026-01-25T22:53:09Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd]
---
# kd chat (Hand window)

Implement kd chat: attach to persistent hand window for current run, create if missing; define MVP Hand process (agent CLI or shell) and write best-effort logs to .kd/runs/<feature>/logs/hand.jsonl.

## Acceptance Criteria

kd chat always attaches to same hand window; hand logging exists or behavior is documented.
