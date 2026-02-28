---
id: "bb0e"
status: closed
deps: [ffc8]
links: []
created: 2026-02-27T11:55:29Z
type: task
priority: 2
closed_at: 2026-02-28T00:26:37Z
---
# Kill legacy runs/ fallback — hard cut (R4)

## Problem

The `runs/` → `branches/` migration left dual-path fallback logic in 6+ places across `state.py` and `cli.py`. This dead weight should be removed with a hard cut.

## Acceptance Criteria

- [ ] All dual-path fallback logic removed from `state.py` (`logs_root`, `sessions_root`, `tickets_root`)
- [ ] All dual-path fallback logic removed from CLI layer
- [ ] `run_root`, `runs_root`, `ensure_run_layout` deleted from `state.py`
- [ ] `ensure_base_layout` no longer creates `.kd/runs/`
- [ ] If `.kd/runs/` exists at runtime, fail fast with clear error message telling user to manually rename
- [ ] No `kd migrate`, no auto-migration
- [ ] All tests pass
