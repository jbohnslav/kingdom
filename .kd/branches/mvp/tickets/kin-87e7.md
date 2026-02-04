---
id: kin-87e7
status: closed
deps: []
links: []
created: 2026-02-04T23:19:45Z
type: task
priority: 2
---
# Add priority range validation to ticket parsing

Ticket priority accepts any integer but should be constrained to 1-3. Add validation in parse_ticket() and CLI create command. Decide whether to raise error or clamp.
