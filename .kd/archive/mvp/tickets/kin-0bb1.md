---
id: kin-0bb1
status: closed
deps: []
links: []
created: 2026-02-04T02:47:35Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# State directory restructure

Add .kd/.gitignore, create logs/council/ in run layout, update ensure_run_layout()

## Acceptance Criteria

- .kd/.gitignore ignores *.json, *.jsonl, runs/**/logs/, worktrees/
- logs/council/ created by ensure_run_layout()
- Existing commands still work
