---
id: kin-31c5
status: open
deps: [kin-ce7d]
links: []
created: 2026-02-04T21:23:33Z
type: task
priority: 2
assignee: Jim Robinson-Bohnslav
---
# Migrate existing .tickets/

Detect .tickets/ directory. kd migrate moves .tickets/*.md to .kd/backlog/tickets/. Verify parse before move. Report failures. Delete source only after success.

## Acceptance Criteria

- [ ] kd migrate handles .tickets/
- [ ] Parse verification before move
- [ ] Clear error reporting for failures
- [ ] Source only deleted after success
- [ ] Warning shown if .tickets/ detected

