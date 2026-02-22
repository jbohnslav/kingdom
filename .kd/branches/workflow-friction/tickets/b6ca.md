---
id: "b6ca"
status: closed
deps: []
links: []
created: 2026-02-17T03:16:11Z
type: task
priority: 2
---
# kd chat: add timestamps to message panels

From audit: docs/chat-tui-polish-audit.md (ticket 8dea).

Messages currently show sender name only. In long conversations, temporal context is lost. Users cannot tell when a response was given or how long a query took.

## Acceptance Criteria

- [x] Finalized message panels show a timestamp (absolute like "14:32" or "Mon 14:32")
- [x] Timestamps come from thread message frontmatter (already has `timestamp` field)
- [ ] Streaming/waiting panels show elapsed time — deferred (ThinkingPanel already has this)
- [x] Timestamps are static on mount (no update overhead)
- [x] No visual clutter — timestamp shown in border title next to sender name

## Worklog

- Added optional `timestamp` param to MessagePanel, shown in border_title as `sender · HH:MM`
- Added `format_timestamp()` helper: HH:MM for today, Mon HH:MM for other days
- History messages use thread timestamp, live messages use now()
- Full suite: 1251 passed
- [17:00] — Closed: Timestamps added to message panels
