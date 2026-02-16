---
from: cursor
to: king
timestamp: 2026-02-16T21:04:52Z
---

The timing race in `run_query` makes perfect sense. If I'm responding quickly (or if the system is under load and the poller ticks are slightly delayed), the stream file is being nuked before the TUI ever gets a chance to read the thinking tokens.

It explains why the behavior was intermittent and why the "snapshot vs delta" theories didn't fully account for it.

Regarding the fix, **Option (C)** (letting the poller handle cleanup) seems like the most robust architectural choice. `poll_streams` is already tracking active streams and handling their lifecycle. If `run_query` simply abandons the file instead of eagerly deleting it, the poller can ensure it reads the final bytes (including any thinking tokens) before it decides the stream is dead and cleans up.

Do we need to add a specific "stream finished" marker or sentinel so the poller knows it's safe to delete, or is the process exit sufficient?
