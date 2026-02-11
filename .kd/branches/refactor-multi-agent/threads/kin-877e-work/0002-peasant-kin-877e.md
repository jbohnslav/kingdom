---
from: peasant-kin-877e
to: king
timestamp: 2026-02-11T02:38:19Z
---

## What I did this iteration

**Bug**: `council_watch` in `cli.py` loaded all historical messages and counted responses from prior ask rounds. When a thread had a previous round where all members responded, then a new `--async ask` was issued, `watch` would immediately report "All members have responded" based on the old responses before any new replies arrived.

**Fix** (in `src/kingdom/cli.py`):
1. After loading all messages, find the sequence number of the last king message (`last_ask_seq`)
2. Only count agent responses with `sequence > last_ask_seq` as having responded to the current ask
3. All messages (including old responses) are still added to `seen_sequences` so the poll loop correctly ignores them

**Test** (in `tests/test_cli_council.py`):
- Added `test_watch_ignores_prior_round_responses` regression test that creates a thread with a complete first round (ask + all member responses), then adds a second king ask with no responses, and asserts that `watch` does NOT claim "All members have responded" and instead shows a timeout.

All 28 tests pass.

## Status: DONE

All acceptance criteria are met:
- `council_watch` now only considers messages after the most recent king ask
- Existing tests continue to pass (no regressions)
- New regression test covers the exact bug scenario
- Changes committed with descriptive message

STATUS: DONE
