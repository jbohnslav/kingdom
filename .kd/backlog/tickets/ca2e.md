---
id: "ca2e"
status: open
deps: []
links: []
created: 2026-03-06T13:35:54Z
type: bug
priority: 2
---
# Hook wrongly nags to log one-off commits against peasant-owned tickets

The post-commit hook suggests logging to a peasant-assigned ticket when the Hand/King does a one-off commit. It should: (1) not suggest peasant-assigned tickets, (2) not nag when there's no Hand/King-active ticket, (3) eventually suggest the epic ticket for cross-ticket work.

## Acceptance Criteria

- [ ]
