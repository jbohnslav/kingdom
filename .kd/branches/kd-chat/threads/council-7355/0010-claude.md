---
from: claude
to: king
timestamp: 2026-02-16T21:10:22Z
---

Cursor's point about ghost streams on restart is valid — I hadn't considered the `on_mount` scenario. If you relaunch `kd chat` and old stream files are still sitting there, the poller would start tracking them, seek to offset 0, and emit all the old deltas again as if they were live. That's a real bug, not a hypothetical.

The two-step fix is clean:

1. Remove the `unlink()` from `run_query`'s `finally` — fixes the race.
2. Glob-delete `.stream-*.jsonl` in `on_mount` — prevents ghost streams on restart.

Both are one-liners. No new abstractions, no timers, no sentinels. And it means during a live session the files persist (so the poller always gets to drain them), but on the next session launch you start clean.

The only thing I'd add: make sure the `on_mount` cleanup happens *before* the poller starts, not concurrently. If `on_mount` kicks off polling in a `run_worker` and then does the glob-delete after, you've got the same race in reverse. But that's just ordering within `on_mount`, not additional complexity.

I think this is the right fix. Two lines of code, directly addresses both the immediate bug and the obvious follow-on issue.
