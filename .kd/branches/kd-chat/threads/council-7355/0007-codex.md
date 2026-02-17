---
from: codex
to: king
timestamp: 2026-02-16T21:08:37Z
---

I’d ship the minimal fix now: stop deleting in `run_query` and defer cleanup to archive.

Why this is still low-risk:
- It directly removes the confirmed race.
- `stream_offsets` already prevents re-emitting old lines during a live session.
- File sizes are tiny, so short-term disk cost is negligible.

One caveat to track:
- If old stream files are left forever, poller scan cost can grow over long threads, and app restarts could re-read historical streams unless startup logic filters them.

Pragmatic path:
1. Do the one-line `unlink` removal now (fixes user-visible bug fast).
2. Add a follow-up hardening ticket: “prune old stream files on archive/startup or only poll active-round streams.”

So yes, your diagnosis is right, and “don’t delete immediately” is the right first move.
