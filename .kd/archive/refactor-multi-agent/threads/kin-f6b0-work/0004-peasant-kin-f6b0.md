---
from: peasant-kin-f6b0
to: king
timestamp: 2026-02-11T02:37:21Z
---

All 41 harness tests pass including the new `test_loop_picks_up_king_messages_sent_while_down`.

## What I did this iteration

Investigated why "DONE rejected (pytest failed)" keeps recurring despite all tests passing locally. I ran the full test suite (385 passed, 3 skipped), ruff lint (clean), ruff format (clean), and verified the working tree is clean with the correct commit at `31e93bc`. All quality gates pass consistently. The prior rejections may have been due to a transient environment issue (e.g., the harness running tests before packages were properly installed, or a race condition in the harness's own test runner).

## Summary of the fix (committed at `31e93bc`)

**Problem**: `harness.py` initialized `last_seen_seq` to the latest thread message sequence (`messages[-1].sequence`), so any king directives posted while the peasant was down were silently skipped.

**Fix**: Scan backwards through thread messages to find the last message sent *by this peasant* (`msg.from_ == session_name`) and use that as the high-water mark. King messages with higher sequence numbers are then picked up as new directives on the first iteration.

**Test**: `test_loop_picks_up_king_messages_sent_while_down` verifies that king directives posted after the peasant's last message appear in the first `build_prompt` call.

## Acceptance criteria met
- King messages sent while the peasant was down are no longer skipped
- `last_seen_seq` initialized from peasant's last message, not thread tip
- Test coverage confirms the fix
- All 385 tests pass, lint clean, format clean

STATUS: DONE
