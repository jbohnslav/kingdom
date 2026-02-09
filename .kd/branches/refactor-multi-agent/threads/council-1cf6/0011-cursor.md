---
from: cursor
to: king
timestamp: 2026-02-09T17:14:49Z
---

Based on the review of `.kd/branches/refactor-multi-agent/design.md` and the current codebase state:

**What has been done:**
*   **T1: Thread model** (`src/kingdom/thread.py`) - Completed and marked `[x]`.
*   **T2: Agent config model** (`src/kingdom/agent.py`) - Completed and marked `[x]`.
*   **T3: Agent session state** (`src/kingdom/session.py`) - **Completed** (code and tests exist), but marked `[ ]` in the design doc. I found the implementation in `src/kingdom/session.py` covering all acceptance criteria including legacy migration.
*   **T5: Peasant execution** (`src/kingdom/harness.py`) - Completed and marked `[x]`.

**What is next:**

The next immediate priority is **T4: Council refactor** (Priority 2).

This task implements the "split-brain" workflow we just designed to prevent the Hand from interfering with Council debates. It involves:
1.  **Refactoring `kd council ask`**:
    *   Unified command (replacing `followup`/`critique`).
    *   Adding `--async` flag to fire-and-forget (returning a thread ID).
    *   Adding `--to <agent>` to target specific members.
2.  **Implementing `kd council show`**:
    *   Displaying the static thread history with Rich panels.
3.  **Implementing `kd council watch`**:
    *   Live-tailing the conversation in a separate terminal.
4.  **Cleaning up**:
    *   Removing the old `followup` and `critique` commands.

After T4 is complete, we will move to **T6: Peasant messaging and supervision** to improve how we interact with running peasants (`msg`, `read`, `sync`).
