---
id: kin-b76b
status: open
deps: []
links: []
created: 2026-02-13T14:08:58Z
type: task
priority: 2
---
# Assign tickets to agents and show current assignment

Add an `assigned` field to ticket frontmatter so tickets can be assigned to agents — a peasant, a council member, or "hand" (the agent the King is currently interacting with). When you run `kd tk show` with no arguments, it should show the ticket currently assigned to you (the hand). This gives context-aware "what should I be working on?" without having to remember ticket IDs.

Peasants already get assigned implicitly via `kd peasant start`, but there's no way to assign a ticket to the hand or a council member for tracking purposes.

## Acceptance Criteria

- [ ] Tickets have an `assigned` frontmatter field (agent name or "hand")
- [ ] `kd tk assign <ticket-id> <agent>` sets the assignment
- [ ] `kd tk show` with no arguments shows the ticket assigned to "hand" (current agent)
- [ ] `kd tk list` shows assignments in output
- [ ] `kd peasant start` sets assignment automatically
- [ ] `kd tk unassign <ticket-id>` clears the assignment
