---
from: cursor
to: king
timestamp: 2026-02-15T02:52:10Z
---

The tickets are significantly improved and the scope for `3e60` (TUI) and `e756` (Streaming) is now crisp and implementable.

However, there is **one critical omission** that will cause bugs in Phase 1 and 2:

### 🔴 Missing Ticket: Harden Thread System for Concurrency

You deferred the "Group Chat" ticket (which is fine), but you **cannot defer the concurrency fix**.

**Why it matters now (Phase 1 & 2):**
Even without Group Chat, `kd council ask` runs agents in parallel. If Claude and Codex finish at the exact same second (which happens more often than you think with small prompts or timeouts), they will both:
1.  Read the thread directory.
2.  See the last message is `005-king.md`.
3.  Both decide to write `006-response.md`.
4.  **Result:** One response overwrites the other. Data loss.

**Action Required:**
Create a ticket for **"Thread system concurrency safety"**.
*   **Priority:** 1 (Blocker for reliable async/parallel execution).
*   **Scope:** Modify `add_message` to use a lock file (`thread.lock`) or atomic file creation strategy (e.g., `link` or `O_EXCL`) to ensure two processes never claim the same message ID.

### Summary of Review

| Ticket | Status | Feedback |
| :--- | :--- | :--- |
| **3e60 (TUI)** | ✅ Good | Correctly scoped to View Layer only. |
| **e756 (Stream)** | ✅ Good | Explicitly mentions code reuse for `extract_stream_text`. |
| **70f6 (Show)** | ✅ Good | Visual separation included. |
| **a9c9 (Status)** | ✅ Good | Concrete checks (PID, exit code) specified. |
| **Concurrency** | ❌ **MISSING** | **Must be added.** Parallel agents will overwrite each other's messages without it. |

**Recommendation:** Create the concurrency ticket, then you are ready to execute.
