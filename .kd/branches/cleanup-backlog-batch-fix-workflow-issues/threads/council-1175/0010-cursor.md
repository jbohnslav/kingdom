---
from: cursor
to: king
timestamp: 2026-02-13T23:39:39Z
---

The implementation is solid and faithfully executes the design, with two specific gaps that should be addressed before merging.

### 1. Does the implementation match the design?
**Yes.** The core logic for Council fixes, Ticket workflow, and Lifecycle changes is correctly implemented.
*   **Council:** The `watch_thread` logic correctly handles the `expected` set (kin-c749), async is opt-in (kin-db3b), and @mentions are parsed (kin-09c9).
*   **Tickets:** `tk move` correctly handles the variadic args + optional target heuristic. `tk pull` and `tk assign` are implemented as specified.
*   **Lifecycle:** `kd done` is correctly switched to a status-only transition (no file moves), resolving the branch protection conflict.

### 2. Bugs or Edge Cases Missed
**A. `kd migrate` should use `git mv`**
The design doc explicitly requires: *"Migration uses `git mv` to preserve file history"*.
The current implementation uses `ticket_file.rename(new_path)` (Python's `os.rename`).
*   **Risk:** Git will likely interpret this as "delete old file" + "create new file" because the file content is *also* changing (rewriting IDs). This breaks the history of every ticket in the repo.
*   **Fix:** Use `subprocess.run(["git", "mv", ...])` when inside a git repo.

**B. `kd tk list` hides done tickets forever**
The design doc states: *"Add `--all` / `--include-done` flags where users need to see archived work."*
The current implementation of `kd tk list --all` **explicitly filters out** done branches:
```python
if branch_dir.is_dir() and not is_branch_done(branch_dir):
    # ... add to list
```
*   **Risk:** Since `kd done` no longer moves branches to `archive/`, "done" branches are just folders in `branches/`. The current logic makes them invisible to the CLI with no way to view them.
*   **Fix:** Add an `--include-done` flag to `ticket_list` and pass it through to the filtering logic.

### 3. Migration & Backwards Compat
*   **`tk move` Compat:** The heuristic to support `tk move <id> <target>` (legacy) vs `tk move <id1> <id2>` (new) works well. It checks if the second argument resolves to a ticket; if not, it assumes it's a target branch. This is a smart, non-breaking change.
*   **Migration Safety:** The regex `\bkin-([0-9a-f]{4})\b` is precise enough to avoid false positives.

### 4. Fixes Required Before Merge
1.  **Update `src/kingdom/cli.py` (`migrate` command):** Change the file rename logic to use `git mv` to preserve history.
2.  **Update `src/kingdom/cli.py` (`ticket_list` command):** Add `--include-done` flag to allow viewing tickets from completed branches.

**Recommendation:** Apply these two fixes, then merge. The rest of the implementation is excellent.
