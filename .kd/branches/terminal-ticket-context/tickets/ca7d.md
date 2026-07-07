---
id: "ca7d"
status: closed
deps: []
links: []
created: 2026-07-05T02:29:50Z
type: bug
priority: 2
closed_at: 2026-07-05T02:32:11Z
assignee: hand
---
# Ignore peasant-owned terminal ticket context

Claude re-review found terminal_context_ticket_is_current only checks status == in_progress. If a ticket was started by hand, then later handed to a peasant, the ticket remains in_progress but assignee becomes peasant-<id>. The terminal context should no longer prompt the hand to log that peasant-owned ticket; this should mirror kd tk current --exclude-peasant fallback behavior.

## Acceptance Criteria

- [x] Terminal context validation rejects tickets assigned to peasant-*
- [x] Stop hook falls back instead of prompting for peasant-owned terminal context
- [x] Regression test covers peasant-assigned started ticket

## Worklog

- 2026-07-05: Started from Claude re-review finding. Current terminal_context_ticket_is_current only requires the recorded ticket to still be in_progress, but peasant handoff keeps status in_progress and changes assignee to peasant-<id>. The terminal-context path needs the same peasant exclusion semantics as kd tk current --exclude-peasant.
- 2026-07-05: Added failing regression for a recorded terminal ticket that remains in_progress but is assigned to peasant-<id>. Updated terminal_context_ticket_is_current to reject peasant-owned tickets so Stop falls back just like kd tk current --exclude-peasant.
- 2026-07-05: Verification passed: uv run pytest tests/test_hook.py::TestStopHandler::test_ignores_peasant_terminal_ticket_context -q; uv run ruff check; uv run pytest -q with 1918 passed, 38 skipped, 1 xfailed.
