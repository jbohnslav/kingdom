---
id: kin-f968
status: closed
deps: [kin-1ecc]
links: []
created: 2026-01-25T22:53:23Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd, tk]
---
# Create tk tickets from plan.md

Parse plan.md tickets into tk create/dep calls; support dry-run and require explicit approval before applying. Decide how to store created ticket ids back into the plan/state.

## Acceptance Criteria

Given a sample plan.md, can generate dry-run commands; with approval, creates markdown tickets and applies dependencies.
