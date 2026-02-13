---
from: cursor
to: king
timestamp: 2026-02-13T22:46:40Z
---

The design doc is solid. It correctly identifies the friction points in the current workflow (especially around Council reliability and the `kd done` git state) and proposes practical fixes.

Here is my review:

### 1. Soundness of Solutions
The proposed solutions are sound and well-targeted.
*   **Council UX:** Reverting to sync-by-default (`kin-db3b`) while properly setting `BASH_DEFAULT_TIMEOUT_MS` is the right move. Async added complexity that isn't worth it if the root cause was just a timeout configuration.
*   **Ticket Workflow:** Dropping the `kin-` prefix (`kin-98e7`) is a great quality-of-life improvement. 4-char hex is sufficient for uniqueness and much faster to type.
*   **Lifecycle:** Auto-committing the archive move in `kd done` (`kin-a321`) is essential. Leaving the user with unstaged file moves after a merge is a leaky abstraction.

### 2. Execution Order
The order is logical.
*   **1-4 (Council Fixes):** Prioritizing the P1 bug and stability issues is correct.
*   **5 (Ticket IDs):** Doing the ID migration early is smart, as it touches filenames and could conflict with other ticket operations if delayed.
*   **9 (kd done):** This can happen anytime, but placing it after the core workflow fixes makes sense.

### 3. Risks & Gaps
*   **`kd done` Auto-commit Scope:** Be very careful with the implementation of `kin-a321`. The auto-commit must **only** stage the moved ticket files (old path and new path). Do not run `git add .`, or you risk committing unrelated work the user has in their working directory.
*   **Ticket Migration:** Ensure the renaming logic uses `git mv` (or equivalent) if possible, to preserve file history, rather than just OS-level moves.
*   **@mentions Parsing:** The parser for `kin-09c9` needs to be robust. Ensure it doesn't accidentally trigger on `@` symbols inside code blocks or email addresses within the prompt.

### 4. Opinions on Open Questions
*   **Migration:** **Prefer a specific command** (e.g., `kd migrate-tickets`) or a prompt on startup ("Legacy ticket IDs found. Migrate? [y/N]"). Silent, automatic migration on every run is risky and can surprise the user.
*   **@all support:** **Yes.** It provides a clear, explicit way to override implicit scoping rules.
*   **Auto-commit default:** **Yes, default to true.** The goal is to remove friction. The "happy path" should be one command. Add a `--no-commit` flag for the rare manual cases.

**Recommendation:** Proceed with the plan. The focus on "hardening" the existing workflow rather than adding new features is exactly what the system needs right now.
