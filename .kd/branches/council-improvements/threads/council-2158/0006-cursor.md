---
from: cursor
to: king
timestamp: 2026-02-15T18:24:16Z
---

The `council-improvements` branch has made significant progress, effectively closing 14 tickets and delivering the core async/retry architecture. The implementation largely matches the design doc's "Phase 1" goals.

However, I have identified **three critical issues** that require attention: one regression, one race condition, and one missing feature from the design plan.

### 1. Regression: Partial Timeout Responses are Ignored
**The Issue:** `AgentResponse.thread_body()` prioritizes text over error. If an agent times out but produced *some* text (e.g., 500 words then dies), the error is suppressed.
**Consequence:** `council retry` relies on the `*Error:` prefix to identify failed members. It will see these partial responses as "success" and **will not retry them**, leaving the user with a cut-off message and no easy way to fix it.
**Recommendation:** Update `thread_body` to include the error marker even if text exists.
```python
# src/kingdom/council/base.py
def thread_body(self) -> str:
    if self.text and self.error:
        return f"*Error: {self.error}*\n\n{self.text}"  # <--- Fix
    if self.text:
        return self.text
    # ...
```

### 2. Bug: Stream File Reset Race Condition
**The Issue:** When `council retry` runs, it unlinks and recreates the stream file. The `watch_thread` loop tracks file positions. If the file is recreated, `watch_thread` may try to seek to the *old* position (e.g., byte 5000) in the *new* file (size 0), causing it to miss the entire new stream until it grows past the old offset.
**Recommendation:** In `watch_thread` (cli.py), check for file reset.
```python
# src/kingdom/cli.py -> read_stream_files
# ...
    try:
        if stream_file.stat().st_size < pos:
            pos = 0  # File was reset
        with open(stream_file, encoding="utf-8") as f:
            f.seek(pos)
# ...
```

### 3. Missing Feature: `council ask` (Sync) is not Streaming
**The Issue:** The design doc leaned towards "always use stream-json for council". Currently, `kd council ask` (without `--async`) uses `query_with_progress`, which calls `c.query()`. This path **does not** write to `.stream-{member}.jsonl` files.
**Consequence:** The new "watch" UX (live streaming text) is only visible during `kd council retry` or `kd council watch`. The primary interaction, `kd council ask`, still uses the old spinner and dumps text at the end.
**Recommendation:** Unify the paths. `council ask` should use the same streaming machinery as `retry`.
*   **Plan:** Create a new task to refactor `council ask` to use `c.query_to_thread` (or the worker+watch pattern) by default, ensuring the rich streaming UX is the standard experience.

### Summary of Actions
1.  **Reopen Ticket 6412**: To fix the partial timeout regression and the stream race condition.
2.  **Create New Ticket**: "Enable streaming for synchronous `council ask`" to fulfill the design doc's intent for a unified streaming experience.
3.  **Code Quality**: The code is otherwise clean, well-structured, and follows project patterns. The `extract_stream_text` logic correctly handles the NDJSON formats described in the design.
