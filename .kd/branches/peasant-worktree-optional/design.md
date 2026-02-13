# Design: Peasant Worktree Optionality

## Goal

Simplify the execution model by introducing a core `kd work <ticket>` command that launches the autonomous loop (RALPH) for a single ticket.

- **`kd work <ticket>`**: Runs the loop in the *current directory*.
    - If run in the root (Hand mode), it works on the main branch.
    - If run inside a peasant worktree, it works on that ticket's branch.
- **`kd peasant start <ticket>`**: Orchestrator command.
    - **Default (Parallel)**: Creates a worktree, then launches `kd work <ticket>` *inside that worktree* (as a background process).
    - **`--hand` (Serial)**: Launches `kd work <ticket>` *in the current directory* (as a background process).

This decouples "environment setup" (peasant start) from "doing the work" (work).

## Context

Currently, `kd peasant start` does too much:
1. Resolves context
2. Creates worktree (or not)
3. Creates thread
4. Seeds thread
5. Launches `kd agent run` (internal command) via `subprocess.Popen`

The internal `kd agent run` command (`cli.py:1630`) is close to what we want `kd work` to be, but it's hidden and coupled to the harness implementation details. Promoting it to a top-level `kd work` command makes the system more composable.

## Requirements

1.  **New Command: `kd work <ticket>`**
    - Runs the autonomous loop for the specified ticket.
    - Uses the current working directory as the workspace.
    - Can be run interactively (foreground) or via `peasant start` (background).
    - Updates session state (working/done/blocked).
    - Seeds the work thread with ticket content on first run (so `kd peasant read` shows context).
    - Must honor `--base` flag — `_resolve_peasant_context` currently hardcodes `Path.cwd()`, needs to accept an explicit base for background launches.

2.  **Refactor `kd peasant start`**
    - Instead of calling `kingdom.harness` directly or `kd agent run`, it should invoke `kd work`.
    - **Parallel**: `mkdir worktree -> git worktree add -> cd worktree -> kd work <ticket> &`
    - **Hand**: `kd work <ticket> &` (in current dir)

3.  **Extract `launch_work_background` helper**
    - The Popen boilerplate (build cmd, open log fds, Popen, close fds) is needed in both `peasant start` and `peasant review --reject`. Extract into a shared helper rather than duplicating inline.

4.  **Clean up dead code**
    - Remove `harness.py:main()` and `__main__` block (nothing calls `python -m kingdom.harness` anymore).
    - Remove empty `agent_app` typer group (`kd agent` has no commands).

## Workflow

**Manual / Debugging:**
```bash
# Developer wants to see the agent work on a ticket in their current terminal
kd work kin-123
# Agent runs in foreground, logs to stdout, edits files in .
```

**Peasant Orchestration (Parallel):**
```bash
# Developer wants to dispatch work
kd peasant start kin-123
# 1. Creates .kd/worktrees/kin-123
# 2. Spawns background process: "cd .kd/worktrees/kin-123 && kd work kin-123"
```

**Hand Orchestration (Serial Background):**
```bash
# Developer wants agent to work in background on current checkout
kd peasant start kin-123 --hand
# 1. Spawns background process: "kd work kin-123" (in current dir)
```

## Decisions

- **Command Name**: `kd work` — simple, active verb. Fits with `kd plan`, `kd design`.
- **Execution**: `kd work` is the atomic unit of labor. `kd peasant` is the manager that assigns workspaces.
- **`launch_work_background` helper**: restores DRY without reverting to the old `launch_harness` (which called `kingdom.harness` directly). New helper calls `kd work` via Popen.
- **`--base` on `kd work`**: required for background launches where cwd may differ from repo root. Interactive mode defaults to cwd.

## Issues Found (Council Review)

Cursor implemented `kd work` and the `peasant start` refactor without being asked. The architecture is correct but has integration gaps:

1. **10 test failures** — 3 in `test_cli_peasant.py` (mock `launch_harness` which no longer exists), 7 in `test_council.py` (council preamble injection changes expected prompt shapes)
2. **`kd work` ignores `--base`** — `_resolve_peasant_context` hardcodes `Path.cwd()`, so `kd work --base /path` from a different directory fails to find tickets
3. **Duplicated Popen boilerplate** — same ~25 lines in `peasant_start` and `peasant_review`
4. **No thread seed in interactive `kd work`** — thread created but not seeded with ticket content
5. **Dead code** — `harness.py:main()`, empty `kd agent` subcommand group
