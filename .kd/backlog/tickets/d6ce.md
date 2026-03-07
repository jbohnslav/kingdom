---
id: "d6ce"
status: open
deps: []
links: []
created: 2026-03-07T15:43:12Z
type: task
priority: 2
---
# Lord idle gate: treat done sessions with in_review tickets as actionable

Codex identified during 2ca9 review: get_completed_peasants() only treats needs_king_review as completed, but kd peasant accept now allows session status done for diverged states. A child with ticket.status=in_review and session.status=done is actionable but the idle gate classifies it as non-actionable. Fix: extend get_completed_peasants() or has_actionable_work() to recognize this state.

## Acceptance Criteria

- [ ]
