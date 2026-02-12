---
from: peasant-kin-acd6
to: king
timestamp: 2026-02-11T02:40:57Z
---

## What I did this iteration

Extracted the repeated ~15-line ticket-resolution + feature-resolution + error-handling preamble from 8 `peasant_*` commands into a shared `_resolve_peasant_context()` helper function in `src/kingdom/cli.py`.

**Changes:**
- Added `NamedTuple` import and created `_PeasantContext` named tuple with fields: `base`, `ticket`, `ticket_path`, `full_ticket_id`, `feature`
- Created `_resolve_peasant_context(ticket_id)` helper that handles `find_ticket` + `AmbiguousTicketMatch` + not-found check + `resolve_current_run` + `RuntimeError` handling
- Refactored all 8 commands (`peasant_start`, `peasant_logs`, `peasant_stop`, `peasant_clean`, `peasant_sync`, `peasant_msg`, `peasant_read`, `peasant_review`) to use the shared helper
- Net reduction: **~95 lines** (57 insertions, 152 deletions)
- All 44 peasant CLI tests pass, ruff passes, pre-commit hooks pass

## Status: DONE

All acceptance criteria met:
- The shared helper function `_resolve_peasant_context` is extracted
- All 8 peasant commands use it instead of the duplicated preamble
- Tests pass (44/44), linting passes, commit is clean

STATUS: DONE
