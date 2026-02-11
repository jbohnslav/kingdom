---
from: peasant-kin-7143
to: king
timestamp: 2026-02-11T02:43:18Z
---

## What I did this iteration

1. Investigated the repeated "pytest failed" rejections — tests pass locally (389 passed, 3 skipped)
2. Added 4 unit tests for the `kingdom.council.worker` module in `tests/test_council.py`:
   - `test_worker_queries_all_members` — verifies the worker dispatches to all council members and writes to thread
   - `test_worker_queries_single_member` — verifies `--to` targets a specific member
   - `test_worker_unknown_member_exits` — verifies exit code 1 for unknown member
   - `test_worker_saves_sessions` — verifies session state is persisted after query
3. Fixed ruff-format issues and committed

## Acceptance criteria

- Double-fork pattern (`os.fork`/`os.setsid`/`os._exit`) completely removed from `council_ask`
- Replaced with `subprocess.Popen + start_new_session=True` matching `peasant_start`/`launch_harness` pattern
- Exceptions propagate properly (no silent swallowing via `os._exit(0)`)
- Cross-platform compatible (no Unix-only syscalls)
- 389 tests pass, all pre-commit hooks pass

STATUS: DONE
