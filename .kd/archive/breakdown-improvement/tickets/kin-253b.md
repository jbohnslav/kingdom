---
id: kin-253b
status: closed
deps: [kin-8084]
links: []
created: 2026-02-05T02:38:45Z
type: task
priority: 2
---
# Remove old breakdown.md infrastructure

Cleanup old parsing code:
- Remove parse_breakdown_tickets() and related parsing code
- Remove build_breakdown_template()
- Remove breakdown.md from state tracking
- Update kd status to reflect new flow

Depends on: kin-8084 (new flow must work before removing old code)
