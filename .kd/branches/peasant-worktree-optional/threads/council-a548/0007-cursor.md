---
from: cursor
to: king
timestamp: 2026-02-12T23:15:12Z
---

It makes perfect sense to have both options! In fact, looking at the codebase, the "Hand Mode" (serial execution) is already implemented via the `--hand` flag in `kd peasant start`.

I have updated the design document to formally define this workflow and confirm that it fits seamlessly into the system.

### Changes Summary

1.  **Design Document (`.kd/branches/peasant-worktree-optional/design.md`)**:
    *   Added **Parallel (Default)** vs **Serial (Hand Mode)** execution models.
    *   Documented that `--hand` runs the agent in the current directory, skipping worktree creation.
    *   Clarified that this is ideal for sequential work or when you want to oversee a trusted agent ("Hand of the King") directly.

2.  **Implementation Verification**:
    *   **CLI (`src/kingdom/cli.py`)**: The `peasant start` command accepts a `--hand` flag. When set, it uses `base` (current dir) as the worktree path instead of creating a new one in `.kd/worktrees/`.
    *   **Harness (`src/kingdom/harness.py`)**: The agent harness respects the `worktree` path passed to it, so it works correctly whether it's in an isolated worktree or the root repo.
    *   **Tests (`tests/test_cli_peasant.py`)**: There is already a test case `test_start_hand_mode` ensuring this works as expected.

### How to use it

*   **Parallel (Peasant):** `kd peasant start kin-123` (Default, creates worktree)
*   **Serial (Hand):** `kd peasant start kin-123 --hand` (Runs in current directory)

This fits perfectly with your desired workflow: you can plan with the Council, then choose to either dispatch multiple peasants in parallel or keep a single "Hand" working serially right in front of you.
