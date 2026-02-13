---
id: kin-c5cb
status: open
deps: []
links: []
created: 2026-02-13T22:47:40Z
type: feature
priority: 1
---
# Replace kd breakdown with agent prompt output

Strip the current breakdown command of all its ticket-parsing/creation logic (parse_breakdown_tickets, --apply, the two-pass create+link algorithm, etc). Instead, kd breakdown should just print a ready-to-paste prompt for a coding agent (Claude Code, Cursor, etc). The prompt should instruct the agent to: read the design doc, use kd tk create/dep CLI commands to turn it into tickets with proper dependencies. This removes a bunch of fragile markdown parsing and leverages the agent to do the smart work. Clean up breakdown.py of unused code (parse_breakdown_tickets, council prompt builders, etc) and remove related tests.
