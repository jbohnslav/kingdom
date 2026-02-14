---
from: cursor
to: king
timestamp: 2026-02-14T02:05:38Z
---

The following unstaged changes have been made to the codebase:

### 1. Increased Timeout (300s → 600s)
The default timeout has been increased from 5 minutes to 10 minutes in four locations:
- `src/kingdom/cli.py`: CLI default for `kd council ask --timeout`
- `src/kingdom/council/worker.py`: Worker argument default
- `src/kingdom/council/council.py`: `Council` class default
- `src/kingdom/council/base.py`: `CouncilMember.query` default

### 2. Implemented Streaming to File
The `CouncilMember.query` method in `src/kingdom/council/base.py` has been rewritten to support real-time streaming to a file:
- **Mechanism:** Switched from `subprocess.run` to `subprocess.Popen` with `select.select` to read output line-by-line.
- **Streaming:** If a `stream_path` is provided, stdout lines are appended to that file immediately as they arrive.
- **Timeout Handling:** On timeout, it now captures any partial output accumulated so far (instead of returning an empty string) and returns it as the response text.

### 3. Wired Up Streaming in Council & Worker
- **Council (`src/kingdom/council/council.py`):** The `query_to_thread` method now creates a temporary file `.stream-{member}.md` in the thread directory and passes it to `query`. It cleans up the file after the full response is received.
- **Worker (`src/kingdom/council/worker.py`):** Similar logic added for the background worker process when targeting a specific member (`--to`).

This implementation ensures that long-running queries stream their progress to disk (recoverable if interrupted) and that timeouts preserve whatever partial work was completed.
