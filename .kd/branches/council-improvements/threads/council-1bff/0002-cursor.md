---
from: cursor
to: king
timestamp: 2026-02-15T13:13:16Z
---

This is a solid improvement to the Council UX, particularly the retry logic and streaming visualization. The retry strategy is sound, and the `thread_body` centralization is a good cleanup.

However, there are a few correctness and consistency issues to address before merging.

### 1. Correctness: Stream File Reset Race Condition
In `watch_thread`, you track `stream_positions[name]`. If a member retries (which `CouncilMember.query` now supports), it unlinks and recreates the stream file.
*   **The Bug:** `watch_thread` will try to `seek(pos)` to the *old* position in the *new* (empty) file. This will likely result in reading nothing (best case) or confused output if the new file grows past the old offset.
*   **Recommendation:** In `read_stream_files`, check if the file size is smaller than `pos`. If so, assume a reset and start from 0.
    ```python
    # Inside read_stream_files loop...
    file_size = stream_file.stat().st_size
    if file_size < pos:
        pos = 0  # File was reset/recreated
    ```

### 2. Design: `council ask` vs `council retry` Inconsistency
`council_retry` uses `c.query_to_thread`, which:
1.  Writes to stream files (enabling `watch`).
2.  Writes final messages to the thread *incrementally* as they finish.

`council_ask` (via `query_with_progress`) uses `c.query`, which:
1.  Does **not** write stream files.
2.  Writes to the thread only after **all** members finish.

*   **The Issue:** The new streaming UX in `watch` will **not work** for the primary `council ask` command, only for `retry` (or if running via `worker`). Also, `ask` feels slower because it batches all writes at the end.
*   **Recommendation:** Refactor `council_ask` to use `c.query_to_thread` (or similar logic). This would unify the behavior, enable streaming for standard queries, and show results incrementally.

### 3. Test Coverage
*   **Missing:** A test case for `CouncilMember.query` where `stream_path` is provided and a retry occurs. Verify that the file is indeed unlinked and started fresh (the code looks correct, but it's a critical path for the fix in #1).

### 4. Minor Nits
*   **`council_retry`**: The `timeout` option is passed to `c.timeout`, but `c.query_to_thread` passes `self.timeout` to `member.query`. This is correct, just verifying the flow.
*   **`watch_thread`**: The `refresh_per_second=4` (0.25s) is good, but ensure `read_stream_files` isn't too I/O heavy if many agents are streaming. (Should be fine for typical council sizes).

### Summary
The retry logic and `watch` improvements are great, but **please fix the stream position bug** and strongly consider **updating `council_ask` to use `query_to_thread`** so the new UX benefits the main workflow, not just retries.
