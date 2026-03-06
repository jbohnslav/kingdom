---
id: "ca2e"
status: in_progress
deps: []
links: []
created: 2026-03-06T13:35:54Z
type: bug
priority: 2
assignee: peasant-ca2e
parent: 1ba2
---
# Hook wrongly nags to log one-off commits against peasant-owned tickets

The post-commit hook suggests logging to a peasant-assigned ticket when the Hand/King does a one-off commit. It should: (1) not suggest peasant-assigned tickets, (2) not nag when there's no Hand/King-active ticket, (3) eventually suggest the epic ticket for cross-ticket work.

## Acceptance Criteria

- [ ]

## Worklog

- [12:20] — Iteration 1/50 — calling agent
  Ticket: Hook wrongly nags to log one-off commits against peasant-owned tickets
