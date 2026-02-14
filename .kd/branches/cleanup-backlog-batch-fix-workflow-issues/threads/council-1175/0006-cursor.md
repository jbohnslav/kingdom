---
from: cursor
to: king
timestamp: 2026-02-13T23:11:02Z
---

This is a classic "filesystem as database" architectural dilemma.

**Recommendation: Option 1 (Status-only, no move).**

You should stop moving files entirely. In a git-backed system, moving a directory to indicate a state change (`active` -> `done`) is an anti-pattern that fights against Git's design.

Here is the analysis of the tradeoffs and the detailed recommendation.

### The Tradeoffs

| Option | Git Workflow | Data Integrity | User Experience | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Current (Move on Master)** | **Broken.** Fails on protected branches. | Good. | Good (clean folders). | **Non-starter.** |
| **1. Status-only (No move)** | **Perfect.** No extra commits, no merge conflicts. | Good. | Mixed (folder clutter). | **Best Choice.** |
| **2. Local-only (Gitignore)** | Good. | **Critical Risk.** History is not synced to remote. | Good. | **Dangerous.** |
| **3. Move in PR** | **High Friction.** Messes up PR diffs (renames); requires post-work steps. | Good. | OK. | **Too heavy.** |

### Why "Status-only" is the Right Design

**1. "Clutter" is a UI problem, not a Storage problem.**
The concern about `.kd/branches/` accumulating directories is valid for a *human* browsing the file explorer, but irrelevant to the *system*.
*   **CLI:** You can easily filter out done branches in `kd list`, `kd start` autocompletion, and `kd status`. The user should rarely need to manually browse `.kd/branches`.
*   **Git:** Git handles thousands of files/folders effortlessly.
*   **History:** You want the history of the branch (design docs, tickets) to persist in the repo.

**2. State belongs in Data, not Location.**
Using the directory path (`branches/` vs `archive/`) to represent the state of an entity is fragile.
*   If you want to "reopen" a branch, you have to move it back.
*   If you want to query "all tickets," you have to search two directory trees.
*   Setting `"status": "done"` in `state.json` is atomic, precise, and doesn't require a filesystem transaction.

**3. Separation of Concerns: Work vs. Maintenance.**
The act of finishing a feature (`kd done`) should not force a repository maintenance task (organizing files).
*   **Workflow:** `kd done` should be instant and local. It marks the metadata as complete.
*   **Maintenance:** If the directory eventually contains 500 folders, that is a separate problem to be solved by a separate process (Garbage Collection).

### Proposed Implementation Plan

1.  **Modify `kd done`:**
    *   Update `state.json` to set `status: "done"` and `done_at: <timestamp>`.
    *   Remove the local git worktrees (cleanup local disk space).
    *   **Do not move the directory.**
    *   Do not create a git commit.

2.  **Update CLI Views:**
    *   Ensure `kd list` hides "done" branches by default (add `--all` or `--archived` flag).
    *   Ensure `kd start` autocompletion ignores "done" branches.

3.  **Introduce `kd gc` (Future/Optional):**
    *   When the repo gets too heavy (e.g., >100 done branches), the user runs `kd gc`.
    *   This command identifies branches marked `done` > 30 days ago.
    *   It deletes them (or moves them to a separate `archive/` folder if you strictly want to keep them) and creates a **single cleanup commit**.
    *   The user opens a "chore: cleanup old branches" PR.
    *   This separates the "daily work" from the "repo hygiene."

### Summary
Stop moving files. It creates more problems (git permissions, diff noise, race conditions) than it solves (visual organization). Treat `.kd/branches` as your database table, and let the CLI handle the filtering.
