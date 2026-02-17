---
from: cursor
to: king
timestamp: 2026-02-16T21:09:52Z
---

I agree with the diagnosis. The race condition in `run_query` is clear and matches the test failure.

Removing the `unlink()` call in `run_query` is the correct immediate fix to ensure the poller sees the final tokens.

However, regarding the "follow-up hardening": if we leave the files, `ThreadPoller` will pick them up on the next `kd chat` run. Since `poll_messages` ignores the old finalized messages (due to the `last_sequence` check), these old streams will render as "ghost" active streams that never finish.

To prevent this regression without complex logic, we should simply clear any existing `.stream-*.jsonl` files in `ChatApp.on_mount` before polling starts. This ensures a clean slate for the session while allowing files to persist *during* the session to fix the race.

So the plan:
1.  **Remove** `stream_path.unlink()` from `run_query` `finally` block.
2.  **Add** a cleanup step in `ChatApp.on_mount` to delete `thread_dir.glob(".stream-*.jsonl")`.

This solves the race and the startup persistence issue in one go.
