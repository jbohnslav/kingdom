---
from: peasant-98f3
to: king
timestamp: 2026-02-14T04:49:51Z
---

## Summary of what I did this iteration

1. **Investigated the bug**: `move_ticket()` used `Path.rename()` which works for same-filesystem moves but raises `OSError` on cross-filesystem moves, potentially leaving the source ticket behind.

2. **Fixed `move_ticket()` in `src/kingdom/ticket.py`**:
   - Added `import shutil`
   - Wrapped `Path.rename()` in a try/except for `OSError`
   - On cross-filesystem failure, falls back to `shutil.copy2()` + `Path.unlink()` to ensure the source is always removed

3. **Added/updated tests**:
   - **`test_cli_ticket.py`**: Added assertion in `test_move_defaults_to_current_branch` to verify the source file is removed from backlog after move
   - **`test_ticket.py`**: Added `test_move_cross_filesystem_fallback` (monkeypatches `Path.rename` to raise `OSError`, verifies copy+delete fallback works and source is removed)
   - **`test_ticket.py`**: Added `test_move_destination_exists` (verifies `FileExistsError` when destination already has the file)

4. **All 486 tests pass**, linting clean, committed.

## Acceptance Criteria Check
- **"The move command should delete the original file after copying to the destination"** — The `move_ticket()` function now guarantees source removal even in cross-filesystem scenarios via the `shutil.copy2` + `unlink` fallback.
- **"Duplicate ID matches on partial lookups"** — With the source reliably removed, `find_ticket()` will no longer find duplicates across locations.

STATUS: DONE
