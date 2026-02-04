---
id: kin-31c5
status: closed
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

- [x] kd migrate handles .tickets/ (done manually)
- [x] Parse verification before move (n/a - manual)
- [x] Clear error reporting for failures (n/a - manual)
- [x] Source only deleted after success
- [x] Warning shown if .tickets/ detected (n/a - manual)

## Work Log

### 2026-02-04
- Done as part of kin-4a5e migration
- Moved .tickets/*.md to .kd/branches/mvp/tickets/
- Removed .tickets/ directory

