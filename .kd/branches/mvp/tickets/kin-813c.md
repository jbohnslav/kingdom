---
id: kin-813c
status: closed
deps: [kin-ce7d]
links: []
created: 2026-02-04T21:23:20Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Add ticket CLI - status changes

Add kd ticket start, close, reopen commands to change ticket status.

## Acceptance Criteria

- [x] All status commands work
- [x] Status persisted to file
- [x] Partial ID matching works

## Work Log

### 2026-02-04
- Added `_update_ticket_status()` helper function
- Implemented `kd ticket start` - sets status to in_progress
- Implemented `kd ticket close` - sets status to closed
- Implemented `kd ticket reopen` - sets status back to open
- All commands support partial ID matching via find_ticket()
- Output shows old → new status transition
- All 143 tests passing

