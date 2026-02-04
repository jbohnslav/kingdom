---
id: kin-cbeb
status: closed
deps: [kin-813c]
links: []
created: 2026-02-04T21:23:23Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Add ticket CLI - relationships and queries

Add kd ticket dep, undep, move, ready, edit commands for dependency management and queries.

## Acceptance Criteria

- [x] Dependency management works
- [x] Move between branches works
- [x] ready correctly filters by deps and status
- [x] Edit opens correct file

## Work Log

### 2026-02-04
- Implemented `kd ticket dep <id> <dep_id>` - adds dependency
- Implemented `kd ticket undep <id> <dep_id>` - removes dependency
- Implemented `kd ticket move <id> <branch|backlog>` - moves ticket
- Implemented `kd ticket ready` - lists open tickets with no open deps
- Implemented `kd ticket edit <id>` - opens in $EDITOR
- All commands support partial ID matching
- All 143 tests passing

