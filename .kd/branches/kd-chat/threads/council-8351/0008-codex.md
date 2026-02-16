---
from: codex
to: king
timestamp: 2026-02-16T18:57:29Z
---

I can’t edit files in this discussion-only mode, but here’s the exact ticket update text to apply.

Replace **Conversation flow** in `.kd/branches/kd-chat/tickets/3b76.md` with:

1. **First king message** -> broadcast (parallel) -> stop, wait for king. No auto-turns.
2. **Follow-up king messages** -> sequential round-robin up to N total member messages -> stop, wait for king. No broadcast on follow-ups.
3. **@member** -> directed to that member only, no auto-turns.
4. **@all** -> same as normal broadcast targeting; follow-up behavior remains sequential-only.

Update **Acceptance Criteria** line about broadcast to:

- [x] Broadcast (parallel) on first king message (and initial exchange behavior), then wait for king.

And keep/clarify follow-up AC as:

- [x] Follow-up king messages: sequential auto-turns up to N messages (default `len(unmuted_members)`), no follow-up broadcast.

If you want, I can apply this directly once file-edit restrictions are lifted.
