---
from: claude
to: king
timestamp: 2026-02-16T21:08:15Z
---

That's actually the simplest option and I think it's the right one. The stream files are small JSONL — a few KB each at most. Leaving them on disk until thread archival costs essentially nothing.

The current `poll_streams` already has the `found_members` cleanup logic that removes stale entries from its tracking dict when files disappear. If we just stop deleting in `run_query`'s `finally` block, the poller will keep reading the file, see the final events (including thinking), emit the deltas, and then... just stop finding new data. The file sits there inert until the thread is archived or the branch is cleaned up.

The only thing we'd need to handle is making the poller idempotent about already-processed content — but it already tracks file offsets (`stream_offsets` dict), so it won't re-emit old events. It'll just seek to the end and find nothing new on subsequent ticks.

So the fix is literally: delete the `unlink()` call in `run_query`'s `finally` block. That's it. No sentinel files, no caching layers, no new cleanup timers. The stream files become durable artifacts of the conversation, which honestly makes them useful for debugging too — you can always go look at what a member actually streamed.

The archival path (`kd` thread cleanup or branch archival) can wipe the whole stream directory when the thread is done.
