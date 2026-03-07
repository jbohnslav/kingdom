---
id: "d6ce"
status: in_review
deps: []
links: []
created: 2026-03-07T15:43:12Z
type: task
priority: 2
assignee: peasant-d6ce
parent: 4d4a
---
# Lord idle gate: treat done sessions with in_review tickets as actionable

Codex identified during 2ca9 review: get_completed_peasants() only treats needs_king_review as completed, but kd peasant accept now allows session status done for diverged states. A child with ticket.status=in_review and session.status=done is actionable but the idle gate classifies it as non-actionable. Fix: extend get_completed_peasants() or has_actionable_work() to recognize this state.

## Acceptance Criteria

- [ ] `get_completed_peasants` recognizes session `done` with ticket `in_review` as completed (not just `needs_king_review`)
- [ ] `has_actionable_work` returns True when a done/in_review peasant exists
- [ ] Tests cover the done+in_review state combination

## Worklog

- [13:29] — Iteration 1/50 — calling agent
  Ticket: Lord idle gate: treat done sessions with in_review tickets as actionable
- 2026-03-07 13:30 — Fixed get_completed_peasants to also match session done + ticket in_review. Added 3 tests: done+in_review found by get_completed_peasants, done without in_review excluded, and done+in_review recognized by has_actionable_work. All 1806 tests pass.
- [13:30] — Now let me read the full `get_completed_peasants` function.Clear. The fix is on line 148: also match `state.status == "done"` when `ticket.status == "in_review"`. Let me also check what ticket statuses are associated with `needs_king_review` to understand the full picture.Now let me add tests. Le...
- [13:30] — Files changed:
  src/kingdom/lord_harness.py |  7 +++++--
   tests/test_lord.py          | 25 +++++++++++++++++++++++++
   2 files changed, 30 insertions(+), 2 deletions(-)
- [13:31] — Council review: APPROVED — awaiting king review
  [claude] APPROVED: ## Code Review: Ticket d6ce — Lord idle gate: done+in_review as actionable
  [codex] APPROVED: Reviewing the `d6ce` patch directly in the ticket worktree. I’m checking the lord idle gate logic and the added tests against the acceptance criteria before deciding whether any targeted reruns are needed.
