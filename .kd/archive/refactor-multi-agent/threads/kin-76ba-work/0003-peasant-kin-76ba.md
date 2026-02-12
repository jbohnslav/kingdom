---
from: peasant-kin-76ba
to: king
timestamp: 2026-02-11T02:36:11Z
---

## What I did this iteration

Ran the full test suite (383 passed, 3 skipped, 0 failed). The implementation from commit `2f38a89` is correct and complete:

1. **`src/kingdom/cli.py`**: `--thread` (str, `'new'` or `None`) replaced with `--new-thread` (bool, default `False`). Validation block removed. `start_new` logic simplified to use the boolean directly.
2. **`tests/test_cli_council.py`**: All test invocations updated from `--thread new` to `--new-thread`. Invalid-value test removed (not applicable for a boolean flag).

All acceptance criteria are met:
- `--thread` flag removed
- `--new-thread` boolean flag added
- All 383 tests pass
- Working tree is clean, changes committed

STATUS: DONE
