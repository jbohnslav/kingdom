---
id: "ef8e"
status: in_progress
deps: []
links: []
created: 2026-02-25T14:09:51Z
type: task
priority: 1
---
# Fix remaining find_project_root() gaps from 5394

Follow-up to 5394. Three gaps identified by both claude and codex during code review.

## Context

Ticket 5394 landed `find_project_root()` with the correct resolution order
(`KD_BASE` → cwd → walk parents → git toplevel → error) and replaced ~45 call
sites. Core logic and tests are solid. These are the stragglers.

## Bug 1 (High): `kd start` swallows invalid `KD_BASE`

`kd start` catches all `ValueError` from `find_project_root()` at cli.py:279 to
support auto-init (no `.kd/` yet → create one). But this also catches the case
where `KD_BASE` is explicitly set to a bogus path, violating the "fail loudly"
contract from 5394.

**Fix:** If `KD_BASE` is set, use strict `require_project_root()` — no auto-init
fallback. Only fall through to auto-init when `KD_BASE` is unset and no `.kd/`
is found organically.

**Repro:** `KD_BASE=/tmp/nonsense kd start test-branch` → should error, currently
auto-inits in cwd.

## Bug 2 (High): Peasant commands still cwd-bound

`resolve_peasant_context()` at cli.py:1838 defaults `base = base or Path.cwd()`.
9 call sites (peasant_start, peasant_stop, peasant_status, peasant_logs, etc.)
pass no `base` argument, so they all resolve against cwd instead of walking up.
Only `kd work` passes `base` explicitly via `require_project_root()`.

**Fix:** Change line 1838 from `base = base or Path.cwd()` to
`base = base or require_project_root()`. The `kd work` caller already passes
`base` explicitly, so its behavior is unchanged.

**Repro:** From a subdirectory, `kd peasant logs <id>` gives wrong error vs
from repo root.

## Bug 3 (Medium): Missing `kd work` cwd regression test

Ticket 5394 spec required a test verifying `kd work` still defaults its worktree
to cwd (the intentional exception). This test was not landed. Low effort to add.

## Acceptance Criteria

- [ ] `kd start` with `KD_BASE` set to an invalid path hard-fails, includes the invalid path in the error, and does not auto-initialize
- [ ] `kd start` with `KD_BASE` unset and no discoverable project keeps current auto-init behavior
- [ ] `resolve_peasant_context()` uses `require_project_root()` as default base (not `Path.cwd()`)
- [ ] Add a peasant regression test that runs the same peasant command from repo root and a nested subdirectory, asserting both resolve the same `.kd` state
- [ ] Add a `kd work` regression test confirming worktree location still defaults to `Path.cwd()`
- [ ] Full test suite passes

## Non-goals

- No behavior change for `kd init`
- No behavior change for `kd work` cwd default semantics
- No behavior change for `setup-skill` discovery logic
