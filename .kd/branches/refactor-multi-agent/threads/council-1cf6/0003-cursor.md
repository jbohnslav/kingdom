---
from: cursor
to: king
timestamp: 2026-02-09T15:46:35Z
---

Based on the smoke test findings in `kin-41f9.md`, I have updated the design document (`.kd/branches/refactor-multi-agent/design.md`) to reflect the necessary improvements for the "v2" (or refined v3) design.

Here is a summary of the updates made to the design:

1.  **Worktree Initialization**:
    *   Updated `kd peasant start` to explicitly run `uv sync` (to install dependencies) and `pre-commit install` (to set up hooks) in the new worktree. This ensures the environment is correct and pre-commit checks run during the agent's work.

2.  **Harness Quality Gates**:
    *   Updated the harness loop description to specify that the agent runs both `pytest` and `ruff` (lint/format).
    *   Updated the **Stop conditions** for "Done" to require that `ruff check` and `ruff format` pass in addition to tests. This aligns the harness's definition of "done" with the Hand's review criteria.

3.  **Reject-Relaunch Workflow**:
    *   Clarified that `kd peasant review --reject` will **automatically restart** the peasant process if it has exited. This ensures the agent immediately picks up the feedback and resumes working without manual intervention.

4.  **Peasant Log Visibility**:
    *   Added a requirement to `kd peasant start` to capture stdout/stderr in a way that ensures the agent's "thought" output is visible in the logs, not just the harness's iteration boundaries.

5.  **Worktree Staleness**:
    *   Added a new command: `kd peasant sync <ticket>`.
    *   This command pulls changes from the parent branch into the worktree, solving the issue where worktrees become stale when the main codebase (e.g., tests) is updated.

The design doc now reflects a more robust runtime that handles the practical issues found during the smoke test.
