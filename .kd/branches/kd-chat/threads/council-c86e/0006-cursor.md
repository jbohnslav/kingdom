---
from: cursor
to: king
timestamp: 2026-02-16T23:52:42Z
---

### Review of Textual Integration Test Suite (Ticket cf1a)

This is a comprehensive and well-structured integration test suite. It correctly leverages Textual's `app.run_test()` and `Pilot` to verify end-to-end behavior, which is a significant improvement over the previous unit-only tests.

**1. Coverage of Scenarios (22 tests / 11 scenarios)**
*   **Assessment:** Excellent coverage. All 11 scenarios from the ticket are represented.
*   **Strengths:**
    *   **Core:** Covers the full lifecycle (send -> wait -> stream -> finalize).
    *   **Behavioral:** Correctly tests slash commands and the tricky "Escape interrupt" logic (including the "second escape exits" case).
    *   **Regression:** Explicit tests for session isolation and speaker label sanitization are crucial.
*   **Gaps:** None found relative to the ticket scope.

**2. FakeMember / Harness Approach**
*   **Assessment:** Solid.
*   **Why:** `FakeMember` correctly simulates the *observable side effects* of a real agent (writing stream files, writing final files) without the overhead/flakiness of spawning subprocesses.
*   **Fragility Risk:** Low. The harness relies on file system state (`tdir.glob(...)`), which is the exact same contract the real app uses. This makes the tests robust to internal refactoring of the app logic as long as the file contract holds.

**3. Test Isolation**
*   **Assessment:** Adequate.
*   **Mechanism:** `tmp_path` fixture ensures each test runs in a fresh directory. `ensure_branch_layout` sets up the necessary structure.
*   **Note:** `FakeMember` instances are created fresh per test via `make_fake_council`.

**4. Improvements & Observations**

*   **Improvement 1: `wait_until` Polling Interval**
    *   *Current:* `interval=0.05` (50ms).
    *   *Context:* Textual's internal timer is often 50-100ms.
    *   *Recommendation:* Increase default interval to `0.1` (100ms) to reduce CPU spin in tests, or keep it tight if 4s total runtime is acceptable. 4s is very fast, so this is minor.

*   **Improvement 2: Explicit `app.poll_updates()` calls**
    *   *Observation:* The tests manually call `app.poll_updates()` after waiting for files.
    *   *Verdict:* **Keep this.** As noted in the ticket ("Timing strategy"), bypassing the internal timer for the assertion step makes the tests deterministic. Relying solely on the background timer would introduce flakiness.

*   **Improvement 3: `TestAutoTurn` Logic**
    *   *Observation:* `TestAutoTurn` waits for `len(list(tdir.glob("[0-9]*-claude.md"))) >= 2`.
    *   *Risk:* This assumes `claude` always responds twice. If the round-robin logic changes (e.g., `codex` goes first), this might flake.
    *   *Recommendation:* Relax the assertion to check for *any* member's second message, or ensure the `fake_council` order is strictly deterministic (it appears to be `["claude", "codex"]`).

**Conclusion:**
The suite is high quality, robust, and ready to merge. No blocking issues.

**Action:**
*   **Approve** the test suite.
*   **Merge** Ticket cf1a.
