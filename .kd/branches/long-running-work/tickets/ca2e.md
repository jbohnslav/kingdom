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
