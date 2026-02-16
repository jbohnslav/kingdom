---
from: cursor
to: king
timestamp: 2026-02-16T19:02:08Z
---

### Analysis of Session Cross-Talk (Ticket 0f27)

The current architecture (single session ID per agent per branch) assumes a linear workflow: one task at a time per branch. `kd chat` breaks this assumption by introducing a long-lived, interactive context that might run concurrently with other tasks (like a background `peasant` worker or a one-off `kd council ask`).

**1. The Right Isolation Boundary: Per-Thread Session Files**
*   **Recommendation:** **Per-Thread.**
*   **Why:** A "thread" in Kingdom represents a distinct conversation or task context. `kd chat` operates on a specific thread ID. `kd council ask` (by default) operates on the branch context (which is effectively a "main" thread). `peasant` workers operate on ticket threads.
*   **Implementation:**
    *   Move session storage from `.kd/sessions/{agent}.json` to `.kd/threads/{thread_id}/sessions/{agent}.json`.
    *   For backward compatibility/default branch actions (`kd council ask` without a specific thread), treat the branch root as the "default thread" or maintain the legacy location for that specific case.

**2. Chat Session Persistence**
*   **Recommendation:** Persist within the thread, isolated from others.
*   **Why:**
    *   **Isolation:** If I'm chatting with Claude about "Architecture" in Thread A, and a peasant is using Claude to "Fix Bug" in Thread B, Claude shouldn't get confused by seeing "Architecture" prompts in its "Fix Bug" session history.
    *   **Persistence:** Within Thread A, I expect Claude to remember our conversation. While `format_thread_history` provides the *textual* context, the *session* context (KV cache, tool use history) is valuable for performance and deeper recall.

**3. Concurrent `kd chat` and `kd council ask`**
*   **Scenario:** User chats in Thread A. User runs `kd council ask` in Thread B (or default).
*   **Handling:** **Fully Isolated.**
    *   They are different conversations. They should not share session IDs.
*   **Scenario:** User chats in Thread A. User runs `kd council ask --thread A`.
*   **Handling:** **Shared.**
    *   If they target the *same* thread, they are participating in the *same* conversation. They should share the session ID (and the lock on it).

**4. Edge Cases & Failure Modes**
*   **Concurrency/Locking:** If `kd chat` is polling/streaming (holding the session lock or active PID), and `kd council ask` tries to use the same thread/session, one must wait or fail.
    *   *Mitigation:* The file locking in `state.py` handles write safety, but `kd council ask` might time out waiting for the lock if `kd chat` is busy.
*   **Zombie Sessions:** If a thread is deleted or archived, its session files must go with it. Moving sessions *into* the thread directory (`.kd/threads/{id}/sessions/`) solves this automatically.
*   **Context Window:** With per-thread sessions, you might have N active sessions for Claude. This increases the risk of hitting rate limits or cost spikes if the user spins up 10 concurrent threads.
*   **"Global" Knowledge:** Sometimes you *want* bleed-over (e.g., "I just told you about this in the other thread").
    *   *Mitigation:* This is a knowledge management problem, not a session problem. Solved by RAG or explicit context injection, not by accidentally sharing a linear session history.

### Summary Recommendation
Refactor session management to be **Thread-Centric**.
1.  Store sessions inside the thread directory: `.kd/threads/{id}/sessions/{agent}.json`.
2.  Update `CouncilMember` and `Agent` to resolve session paths based on the active `thread_id`.
3.  Retain the branch-level `.kd/sessions/` only for the "default/main" branch context (legacy `kd council ask` behavior).
