---
id: kin-ac22
status: closed
deps: []
links: []
created: 2026-01-25T22:50:36Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd]
---
# kd CLI skeleton + command routing

Create Python package layout + Typer entrypoint for kd; add MVP subcommand stubs: start/chat/council/plan/peasant/dev/status/attach.

## Acceptance Criteria

kd --help lists MVP commands; each command validates input and errors clearly.

