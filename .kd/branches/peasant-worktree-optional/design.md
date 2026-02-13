# Design: Peasant Worktree Optionality

## Goal

Make worktree-based parallel execution optional. After planning/design/breakdown, the user chooses an execution mode:
- **Parallel**: peasants work tickets concurrently in separate worktrees (existing default)
- **Serial (Hand)**: the King's preferred agent works tickets one at a time in the current directory

The planning, design, council iteration, and ticket breakdown phases are identical. The only fork is at "run the tickets."

## Context

The `--hand` flag on `peasant start` already exists (`cli.py:1053`). When set, it uses `base` as the worktree path instead of creating one (`cli.py:1079-1080`). The harness respects whatever path it's given (`cli.py:960`, `harness.py`). A test covers the basic path (`test_cli_peasant.py:81`).

However, hand mode is a per-command flag today, not a first-class execution mode. Several commands assume worktrees exist and break or behave oddly in hand mode:
- `peasant review --reject` hardcodes worktree path lookup for relaunch (`cli.py:1533`)
- `peasant review` runs tests/diff against worktree path (`cli.py:1550-1552`)
- `peasant clean` tries to remove a worktree that doesn't exist
- `peasant sync` looks for a worktree directory (`cli.py:1343`)
- No guard prevents running multiple hand-mode workers in the same directory

## Requirements

1. **Persist `hand` flag in session state** — `update_agent_state` records `hand=True` so downstream commands (review, clean, sync) know the mode without re-specifying it
2. **Serial guard** — refuse `peasant start --hand` if another hand-mode peasant is already active in the same base directory
3. **Review uses stored worktree path** — `peasant review` (tests, diff, reject/relaunch) uses the path from session state (`base` for hand, worktree for parallel), not hardcoded worktree lookup
4. **Clean/sync no-op in hand mode** — exit 0 with informational message, not an error
5. **`peasant start-ready`** — new convenience command that starts all `ready` tickets. Default fans out in parallel. With `--hand`, runs serially (start, wait for completion, start next).

## Non-Goals

- Changing the planning/design/breakdown workflow
- Foreground streaming of agent output (future enhancement)
- Run-level config for execution mode (per-command flag is sufficient for now)
- Renaming "peasant" commands for hand mode — the Hand is still dispatched through the peasant system

## Decisions

- **`--hand` flag name**: fits the Kingdom theme — Hand of the King, a trusted singular assistant
- **Hand flag persisted in AgentState, not run-level state**: simpler, each session knows its own mode
- **`start-ready` is a new command, not a flag on `start`**: `start` takes a single ticket, `start-ready` operates on the queue — different semantics
- **Clean/sync exit 0 in hand mode**: not an error, just nothing to do
- **Safety**: `remove_worktree` must never be called on the base directory

## Workflow

```
Planning (unchanged)          Execution (choose one)
─────────────────────         ─────────────────────
kd council ask ...            Parallel:
kd design                      kd peasant start kin-a1 --agent claude
kd breakdown                   kd peasant start kin-b2 --agent claude
kd ticket ready                 (background, separate worktrees)

                              Serial (Hand):
                                kd peasant start kin-a1 --hand
                                 (wait for completion)
                                kd peasant start kin-b2 --hand

                              Or:
                                kd peasant start-ready --hand
                                 (runs all ready tickets serially)
```

## Open Questions

- Should `start-ready --hand` auto-accept passing tickets and continue, or pause for review between each?
