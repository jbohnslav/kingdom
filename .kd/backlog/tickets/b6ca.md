---
id: "b6ca"
status: open
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

- [ ] Finalized message panels show a timestamp (relative like "2m ago" or absolute like "14:32")
- [ ] Timestamps come from thread message frontmatter (already has `timestamp` field)
- [ ] Streaming/waiting panels show elapsed time (ThinkingPanel already has this; extend to others)
- [ ] Timestamps update as conversation progresses (or are static on mount)
- [ ] No visual clutter — timestamps should be subtle (muted color, small)
- [ ] Medium effort: ~1 hr
