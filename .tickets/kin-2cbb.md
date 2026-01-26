---
id: kin-2cbb
status: closed
deps: [kin-ac22]
links: []
created: 2026-01-25T22:53:02Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd, tmux]
---
# tmux orchestration helpers

Implement tmux server/session/window helpers per docs/tech-stack.md: server per repo (kd-<project>), session per feature, fixed window names (hand/council/peasant-1), deterministic attach.

## Acceptance Criteria

kd start creates/reuses correct tmux session without clobbering others; attach targets resolve deterministically.

