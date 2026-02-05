---
id: kin-49f1
status: closed
deps: [kin-2cbb, kin-c6d0]
links: []
created: 2026-01-25T22:53:15Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
tags: [mvp, kd, council, tmux]
---
# kd council (claude/codex/agent + synthesis)

Implement kd council: create council tmux window with panes for claude/codex/agent plus a synthesis pane (default claude unless configured). Persist outputs to .kd/runs/<feature>/logs/council.jsonl (MVP best-effort).

## Acceptance Criteria

kd council opens expected panes; missing CLIs fail with actionable error messages.

