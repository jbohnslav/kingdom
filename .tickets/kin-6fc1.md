---
id: kin-6fc1
status: open
deps: [kin-55a3]
links: []
created: 2026-02-04T21:23:10Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Create ticket model

Create src/kingdom/ticket.py with Ticket dataclass, generate_ticket_id(), parse_ticket(), serialize_ticket(), read_ticket(), write_ticket(). Same YAML frontmatter format as tk.

## Acceptance Criteria

- [ ] Ticket dataclass defined
- [ ] Can parse existing tk ticket files
- [ ] Can serialize back to same format
- [ ] ID generation doesn't collide with existing
- [ ] Unit tests for parsing edge cases

