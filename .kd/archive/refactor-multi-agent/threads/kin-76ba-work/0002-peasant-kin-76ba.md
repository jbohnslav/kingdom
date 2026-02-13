---
from: peasant-kin-76ba
to: king
timestamp: 2026-02-11T02:35:52Z
---

## Summary

### What I did this iteration
Verified that the ticket's work was already completed in commit `2f38a89`. The changes:

1. **`src/kingdom/cli.py`**: Replaced `--thread` (str option accepting `'new'` or `None`) with `--new-thread` (boolean flag, default `False`). Removed the validation block for invalid `--thread` values. Updated the `start_new` logic to use the boolean directly.
2. **`tests/test_cli_council.py`**: Updated test invocations from `--thread new` to `--new-thread`. Removed the `test_ask_invalid_thread_value_fails` test (no longer applicable since it's a boolean flag).

All 26 council CLI tests pass. Working tree is clean.

### Status: DONE
All acceptance criteria are met:
- The `--thread` flag has been replaced with `--new-thread` boolean
- Tests updated and passing
- Changes committed with a descriptive message

STATUS: DONE
