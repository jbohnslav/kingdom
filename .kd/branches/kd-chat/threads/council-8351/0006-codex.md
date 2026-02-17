---
from: codex
to: king
timestamp: 2026-02-16T18:56:59Z
---

Agreed. With your clarification, implementation is correct and the issue is spec drift in ticket `3b76`.

What should change in the ticket text:
1. `.kd/branches/kd-chat/tickets/3b76.md:21`
   Change follow-up flow to: `follow-up king messages -> sequential round-robin up to N -> stop` (no broadcast).
2. `.kd/branches/kd-chat/tickets/3b76.md:23`
   Remove/adjust the `@all` “explicit broadcast on follow-up” rule, since that conflicts with the behavior you want.
3. `.kd/branches/kd-chat/tickets/3b76.md:43`
   Replace “Broadcast on every king message” with “Broadcast on first exchange only (or when explicitly configured otherwise).”

So: code/tests stand; ticket wording should be corrected to match the intended UX (avoid the automatic 6-message burst).
