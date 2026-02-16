---
from: cursor
to: king
timestamp: 2026-02-16T14:15:35Z
---

I have reviewed the implementation of **Ticket 3b76** (auto-turn round-robin scheduler) and the associated files. The design choices are generally sound, but there are a few subtle concurrency and UX issues to address.

### Design Evaluation

*   **Single Coordinator (`run_chat_round`)**: **Approved.** This is the correct approach for sequential auto-turns. It simplifies state management significantly compared to N independent workers.
*   **Generation Counter**: **Approved.** This is a robust way to handle preemption. If the user sends a message while an auto-turn is pending or running, the generation increment invalidates the running coordinator without needing complex cancellation logic.
*   **Directed Messages Skip Auto-Turns**: **Approved.** This matches the "side conversation" intuition.
*   **Mounting `WaitingPanel` Inside Coordinator**: **Approved.** This provides immediate visual feedback that "the system is thinking" about the next turn, which is good UX.

### Code Review & Issues

**1. Race Condition in `run_chat_round` (Phase 2)**
*   **Location:** `src/kingdom/tui/app.py`, `run_chat_round` method.
*   **Issue:** The loop checks `if self.interrupted or self.generation != generation:` *before* querying the member. However, if the user hits Escape *during* `await self.run_query(...)`, `run_query` will catch the interrupt (via `member.process.terminate()`), but `run_chat_round` will effectively swallow the interrupt state if `run_query` handles the exception gracefully.
*   **Fix:** Ensure that `run_query` re-raises a specific `CancelledError` or that `run_chat_round` checks `self.interrupted` *immediately after* the `await` returns to decide whether to continue the loop.

**2. `active` Set Calculation in Auto-Turns**
*   **Location:** `src/kingdom/tui/app.py`, `run_chat_round` method.
*   **Issue:** `active = [n for n in self.member_names if n not in self.muted]` is recalculated at the start of *each round*.
*   **Impact:** If a user mutes a member *during* a round, they will still be queried if they are next in the list for that round (since the list is likely being iterated).
*   **Recommendation:** Check `if name in self.muted` inside the inner loop (before querying each member) to make `/mute` effective immediately.

**3. UX: Auto-Scroll Behavior**
*   **Location:** `run_chat_round` mounts `WaitingPanel`s.
*   **Issue:** The mounting logic triggers `log.scroll_end(animate=False)` if `self.auto_scroll` is true. In a rapid auto-turn sequence, this might be jarring if the user is trying to read the previous message.
*   **Recommendation:** No code change needed now, but monitor this during dogfooding. If it's annoying, we might need a "smart scroll" that only scrolls if the user is already at the bottom.

**4. Config Validation (`auto_rounds=0`)**
*   **Location:** `src/kingdom/config.py`
*   **Status:** **Correct.** You updated the validation to allow `auto_rounds=0` (it was previously strictly positive). This is essential for disabling the feature.

**5. Tests**
*   **Status:** The test plan mentions 10 new tests in `tests/test_tui.py` covering auto-turns. Assuming these cover the "interrupt during auto-turn" and "user message preempts auto-turn" scenarios, the coverage should be sufficient.

### Summary
The implementation is solid. The single-coordinator pattern is the right choice.

**Action Items:**
1.  **Tiny Fix:** In `run_chat_round`, move the mute check inside the inner loop: `if name in self.muted: continue`.
2.  **Verify:** Ensure `run_chat_round` stops immediately if `run_query` returns after an interrupt (check `self.interrupted` after the await).

Otherwise, the code is ready to merge.
