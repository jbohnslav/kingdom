---
from: claude
to: king
timestamp: 2026-02-09T17:55:52Z
---

Now I have the full picture. Here's the assessment:

## Where We Stand

The design doc has been updated with two new requirements based on smoke test findings (lines 303-309):
- Harness quality gates must match review gates (pytest + ruff)
- Harness logging must include test output

And T4/T6 descriptions were refined with `--async`, `kd council watch`, and the dead-peasant warning.

## What's Fixed (from kin-41f9 findings)

| Smoke test bug | Status |
|---|---|
| Peasant file write permissions | **Fixed** — `build_command(skip_permissions=True)` for peasants |
| Council skip-permissions | **Fixed** — council uses `skip_permissions=False` |

## What's Still Broken (7 items)

These are the remaining issues surfaced by the smoke test, grouped by where the fix lives:

### Peasant start setup (bugs 3, 4, 5)
The design doc says `kd peasant start` should run `uv sync` and `pre-commit install` in the worktree (line 273). It doesn't. This causes three cascading failures:
- **Stale worktrees** — no sync, no way to pick up parent branch changes
- **Wrong editable install** — tests import from main repo, not worktree
- **No pre-commit hooks** — peasant commits unformatted code

These are all the same fix: add a setup phase to `peasant_start()`.

### Harness quality gates (bug 7)
`run_tests()` only runs pytest. `kd peasant review` runs pytest + ruff. Peasant claims DONE, passes the harness check, then gets bounced by review. The design doc now explicitly requires the harness to run both (line 307). This was the most painful bug in the smoke test — the peasant looped 8 times saying DONE.

### Harness logging (bug 2)
Test output is appended to the worklog but truncated to 200 chars. The actual failure output isn't logged to stderr. Debugging from logs is impossible. The design doc now requires full test/lint output in logs (line 309).

### Review --reject relaunch (bug 6)
`--reject` sends feedback and sets status to "working" but doesn't restart the harness process. The peasant is dead. The design doc says reject should auto-restart if the process has exited (line 341).

### Dead peasant warning (bug 8)
`kd peasant msg` writes to the thread silently even when the peasant isn't running. The updated T6 description (line 437) says it should warn.

### T4 new acceptance criteria (not yet implemented)
The T4 description was updated to include `--async` and `kd council watch`. Those were partially built (async dispatch exists per commit 7c8a309) but the acceptance checkboxes are still unchecked — need to verify what's done vs. what still needs work.

## Recommended Next Ticket

The highest-impact work is a **harness hardening** ticket covering bugs 4, 5, 6, 7, and 2 — the peasant start setup, quality gate mismatch, logging, and reject-relaunch. These are what made the smoke test painful. Stale worktrees (bug 3 / `kd peasant sync`) and the dead-peasant warning (bug 8) are lower priority since they're edge cases with manual workarounds.

Then re-run the smoke test (kin-41f9).
