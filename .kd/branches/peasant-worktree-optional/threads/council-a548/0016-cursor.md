---
from: cursor
to: king
timestamp: 2026-02-13T12:59:12Z
---

I have implemented the `kd work` command and refactored `kd peasant start` to use it.

### Summary of Changes

1.  **Updated Design Doc**:
    *   Defined the new `kd work <ticket>` command as the atomic unit of execution.
    *   Clarified that `kd peasant start` is now an orchestrator that sets up the environment (worktree or current dir) and then calls `kd work`.

2.  **Implemented `kd work` in `src/kingdom/cli.py`**:
    *   Replaced the internal `agent_run` command with a public `work` command.
    *   It accepts a ticket ID and optional context (agent, worktree, thread, session).
    *   If run interactively (without context flags), it defaults to the current directory ("Hand Mode") and sets up the necessary thread/session state automatically.
    *   This allows you to simply run `kd work kin-123` in your terminal to have the agent work on a ticket right in front of you.

3.  **Refactored `kd peasant start`**:
    *   Removed the `launch_harness` helper function.
    *   Now constructs a `subprocess.Popen` call that invokes `kingdom.cli work ...`.
    *   This ensures that both parallel (peasant) and serial (hand) modes use the exact same execution logic via the `kd work` command.
    *   Updated `peasant review --reject` to also use this new invocation pattern for relaunching agents.

4.  **Verification**:
    *   Ran the existing `tests/test_cli_peasant.py` suite, which covers `peasant start` (both normal and `--hand` modes), `peasant review`, and other lifecycle commands. All tests passed, confirming the refactor didn't break existing functionality.

### How to use it

*   **Parallel (Peasant):** `kd peasant start kin-123` (Same as before, runs in background worktree)
*   **Serial (Hand - Orchestrated):** `kd peasant start kin-123 --hand` (Same as before, runs in background in current dir)
*   **Serial (Hand - Interactive):** `kd work kin-123` (New! Runs in foreground in current dir, logs to stdout)

This structure gives you the flexibility to plan with the Council and then execute however fits your current context best.
