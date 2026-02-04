---
id: kin-81fd
status: closed
deps: []
links: []
created: 2026-02-04T20:03:29Z
type: task
priority: 2
assignee: Jim Robinson-Bohnslav
---
# Improve kd status output for agent context

Enhance kd status to provide agents with all the context they need to understand the current state and what to work on next.

## Acceptance Criteria

- Show current git branch
- Show file path to design.md (so agent can read it)
- Show list of unblocked tickets (via tk ready)
- If a peasant is assigned to a ticket, show that specific ticket ID prominently as 'Your current assignment'
- Support --json flag for machine-readable output
- Reference the CLI design doc at docs/cli-skill-architecture.md

