---
id: "ca2e"
status: in_review
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
- 2026-03-06 12:24 — Fixed the hook nag issue. Added --exclude-peasant flag to kd tk current that filters out peasant-assigned tickets and falls back to the branch's epic ticket. Updated handle_stop to use it. 4 new tests, full suite green (1778 passed).
- [12:24] — Now let me understand how `kd tk current` works and how ticket assignees are stored.Let me understand the epic/parent ticket structure and how branches relate to epics.Now I have a clear picture. The `handle_stop` hook calls `kd tk current --id` which returns the first in-progress ticket regardle...
- [12:24] — Files changed:
  src/kingdom/cli/hook.py          |   2 +-
   src/kingdom/cli/ticket.py        |  13 +++++
   tests/test_cli_ticket_current.py | 102 +++++++++++++++++++++++++++++++++++++++
   3 files changed, 116 insertions(+), 1 deletion(-)
- [12:26] — Council review: BLOCKING (bounce 1/3) — returning to working
  [codex] BLOCKING: I’m reviewing the `ticket/ca2e` patch directly now. The key question is whether the new `tk current` filtering actually matches the hook’s intended behavior without changing the default ticket-selection semantics elsewhere.
  [claude] APPROVED: Let me check the surrounding context in `handle_stop` to see how the result is used.Good. Now let me read the full `ticket_current` function for context.## Code Review: Ticket ca2e — Hook nag fix for peasant-assigned tickets
- [12:26] — Iteration 2/50 — calling agent
  Bouncing on council feedback (1 blocking, 1 approved) — see review above
- 2026-03-06 12:28 — Council bounce addressed: removed epic fallback from --exclude-peasant. The ticket says 'eventually suggest the epic' — that's future work, not this fix. Now when only peasant tickets exist, the hook fails open (no nag). Full suite green (1777 passed).
- [12:28] — The council correctly identified that the epic fallback in `ticket_current` reintroduces the nag — the ticket says "not nag when there's no Hand/King-active ticket" and only "eventually" suggest the epic. I removed the epic fallback logic from `ticket_current` so `--exclude-peasant` now purely fi...
- [12:28] — Files changed:
  src/kingdom/cli/ticket.py        |  7 -------
   tests/test_cli_ticket_current.py | 33 +--------------------------------
   2 files changed, 1 insertion(+), 39 deletions(-)
- [12:28] — Council review: APPROVED — awaiting king review
  [claude] APPROVED: Clean diff after the bounce. The epic fallback is gone — now it's a pure filter.
  [codex] APPROVED: I’m re-reviewing the updated `ticket/ca2e` worktree now, focused on whether the epic fallback is fully gone and whether the hook now truly fails open when only peasant-owned work is active.
