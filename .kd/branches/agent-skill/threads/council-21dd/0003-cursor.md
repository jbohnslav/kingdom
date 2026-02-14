---
from: cursor
to: king
timestamp: 2026-02-14T02:01:25Z
---

I have completed the task.

1.  **Increased Council Timeout:**
    *   Updated the default timeout from 300s (5 minutes) to 600s (10 minutes) in `src/kingdom/cli.py`, `src/kingdom/council/worker.py`, `src/kingdom/council/base.py`, and `src/kingdom/council/council.py`.

2.  **Implemented Streaming to File:**
    *   Modified `CouncilMember.query` in `src/kingdom/council/base.py` to accept an optional `stream_path`.
    *   Switched from `subprocess.run` to `subprocess.Popen` with `select` to stream stdout line-by-line to the file (if provided) while accumulating the full response.
    *   Added logic to capture any remaining output upon timeout, ensuring partial responses are preserved.

3.  **Wired Up Streaming in Council & Worker:**
    *   Updated `Council.query_to_thread` in `src/kingdom/council/council.py` to generate a temporary stream file (`.stream-{member}.md`) in the thread directory and pass it to `query`.
    *   Updated `src/kingdom/council/worker.py` to support streaming when using the `--to` flag.
    *   Added cleanup logic: the stream file is deleted after a successful response is written to the thread history. If the process times out or crashes, the partial response is either returned (and saved to history) or the stream file remains as a recovery artifact.

This ensures that intermediate outputs are captured, and if a timeout occurs, the partial response is saved to the thread history, allowing you to "pick up where you left off" by asking the agent to continue.
