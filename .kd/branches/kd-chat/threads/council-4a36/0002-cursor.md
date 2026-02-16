---
from: cursor
to: king
timestamp: 2026-02-15T23:51:42Z
---

The implementation of Phase 1 is well-structured and largely matches the design document. The modular separation between `app.py`, `poll.py`, and `widgets.py` is clean and follows the plan. However, I have identified two critical bugs in the core message loop that will prevent the feature from working correctly.

### Analysis & Recommendations

**1. Critical Bug: Missing Persistence & Stream Cleanup (`app.py`)**
*   **Issue:** In `ChatApp.run_query`, the code calls `member.query()` but **does not write the response to the thread file** upon success. It also **does not delete the stream file** after the query completes.
*   **Impact:**
    *   Messages will never be finalized in the UI (they will likely get stuck in a "Streaming" or "Waiting" state because `poll.py` waits for a finalized message file to appear).
    *   Messages will not persist to disk, breaking `kd council show` and session resumption.
    *   The `poll.py` logic will be confused by old stream files persisting into subsequent turns.
*   **Recommendation:** Reopen ticket `16e1`. Update `run_query` to:
    1.  Call `add_message(...)` with the response text upon success.
    2.  Unlink (delete) the `stream_path` file in a `finally` block or after the query returns.

**2. Logic Flaw: Polling & Multi-turn Streams (`poll.py`)**
*   **Issue:** `ThreadPoller.poll_streams` skips members present in `self.finalized_members`.
*   **Impact:** If a member is finalized in Turn 1, they are added to `finalized_members`. In Turn 2, if they start streaming again, `poll_streams` will ignore them because `finalized_members` is never cleared.
*   **Recommendation:** Reopen ticket `fe84`.
    *   If you implement stream file deletion (Recommendation #1), you can likely remove the `finalized_members` check in `poll_streams` entirely (since the file won't exist if it's finalized).
    *   Alternatively, clear `finalized_members` when a file reset (size < offset) is detected, ensuring new turns are picked up.

**3. Code Quality**
*   **Strengths:** The code is Pythonic, uses `asyncio` correctly with `to_thread`, and leverages `Textual`'s reactive patterns well. `CouncilMember` correctly captures the Popen handle for the upcoming interrupt feature.
*   **Efficiency:** The polling interval (100ms) and delta extraction are efficient.

### Action Plan

I am reopening the following tickets to address the bugs before proceeding to Phase 2:

1.  **Reopen `16e1`**: Fix `run_query` to write messages and delete stream files.
2.  **Reopen `fe84`**: Fix `ThreadPoller` to handle multi-turn stream detection correctly (likely by relying on file deletion).

Once these are fixed, the core chat loop should be fully functional, and you can proceed to the auto-turn scheduler (`3b76`).
