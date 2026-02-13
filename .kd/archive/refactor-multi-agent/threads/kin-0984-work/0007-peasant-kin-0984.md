---
from: peasant-kin-0984
to: king
timestamp: 2026-02-11T02:48:25Z
---

## What I did this iteration

**Root-caused the persistent pytest failure**: The validation environment runs pytest from the main repo root (`/Users/jrb/code/kingdom/`), not the worktree. The `ProcessPoolExecutor` workers inherited the parent's `sys.path`, so they imported `kingdom.state` from the main repo (which lacks `locked_json_update`) instead of the worktree's version. This caused `ImportError: cannot import name 'locked_json_update' from 'kingdom.state'`.

**Fix**: Replaced `ProcessPoolExecutor`-based concurrency tests with `subprocess.Popen` workers that run an inline Python script. The script explicitly prepends the worktree's `src/` directory to `sys.path` before importing, ensuring the correct `kingdom.state` is used regardless of where pytest is invoked from.

## Acceptance criteria
- `update_agent_state` uses `fcntl.flock` advisory locking via `locked_json_update()` — TOCTOU race eliminated
- `set_current_thread` also uses locked update for shared `state.json`
- `write_json` uses atomic rename with pid-unique temp filenames
- Cross-process concurrency tests prove no updates are lost (40 and 20 concurrent workers)
- All 386 tests pass from both worktree AND main repo root
- ruff lint/format clean, all pre-commit hooks pass

STATUS: DONE
