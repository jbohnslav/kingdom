---
from: cursor
to: king
timestamp: 2026-02-09T18:56:15Z
---

The design doc and the proposed tickets cover most of the issues found in the smoke test, but there are a few gaps and clarifications needed:

**1. kin-9a32 [P1] — Harness logging and quality gates**
*   **What's covered:** Logging agent output, running ruff in DONE check, failure details.
*   **What's missing:** **Permissions**. The smoke test explicitly failed because the agent didn't have write permissions. The design doc states "Skip-permissions flags should only be passed for peasant execution," but `kin-9a32` doesn't explicitly mention implementing this.
*   **Recommendation:** Add "Pass permission flags (e.g., `--dangerously-skip-permissions`) to backend agent" to the acceptance criteria for this ticket.

**2. kin-cebe [P2] — Review --reject auto-relaunch and dead peasant warnings**
*   **What's covered:** Auto-restarting on reject, warning on messaging dead peasants.
*   **What's missing:** Nothing major. This covers the "dead peasant" UX issues well.

**3. kin-0360 [P3] — Peasant sync**
*   **What's covered:** `kd peasant sync` command.
*   **What's missing:** **Worktree Setup**. The design doc now requires `kd peasant start` to run `uv sync` and `pre-commit install`. This is a critical fix for the "stale worktree" and "missing hooks" issues found in the smoke test. While `kin-0360` handles *syncing*, the *initial setup* fix in `kd peasant start` needs a home.
*   **Recommendation:** Explicitly add "Update `kd peasant start` to run `uv sync` and `pre-commit install`" to `kin-0360` (renaming it to "Peasant sync & setup") or `kin-9a32`. Putting it in `kin-0360` makes sense as "environment management".

**4. Missing: Council Refactor (T4)**
*   You asked "are we missing anything?" in the context of "what is next". While T4 (kin-111b) is in the design doc, it is **not implemented yet**. The new tickets address the *peasant* issues, but the *council* improvements we designed (async/watch) are still pending in T4.
*   **Recommendation:** Don't forget that **kin-111b (Council Refactor)** is still a P2 priority that needs to be done after the P1 peasant fixes.

**Summary of Missing Items:**
1.  **Permissions flag** in `kin-9a32`.
2.  **`kd peasant start` setup (uv sync/pre-commit)** in `kin-0360`.
3.  **T4 (Council Refactor)** is the next major feature block after these fixes.
