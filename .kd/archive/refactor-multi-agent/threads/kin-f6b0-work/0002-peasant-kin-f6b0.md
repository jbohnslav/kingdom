---
from: peasant-kin-f6b0
to: king
timestamp: 2026-02-11T02:36:11Z
---

All pre-commit hooks passed and the commit succeeded.

## What I did this iteration

1. **Analyzed the bug**: The original code at line 287 set `last_seen_seq = messages[-1].sequence` (the latest thread message), which meant any king directives posted after the peasant's last message but before the peasant restarted were skipped — their sequence was `<=` the high-water mark.

2. **Verified the fix**: The working tree already contained the correct fix — scanning backwards through messages to find the last message sent *by this peasant* (`msg.from_ == session_name`) and using that as the high-water mark. This ensures king messages with higher sequence numbers are picked up as new directives.

3. **Verified test coverage**: A new test `test_loop_picks_up_king_messages_sent_while_down` validates the scenario: peasant sends a message (seq 2), king sends a directive (seq 3), and when the harness starts, the directive appears in the first `build_prompt` call.

4. **Ran quality gates**: All 41 tests pass, ruff lint is clean, and all pre-commit hooks pass.

5. **Committed**: `31e93bc fix: initialize last_seen_seq from peasant's last message, not thread tip`

## Acceptance criteria met
- King messages sent while the peasant was down are no longer skipped
- `last_seen_seq` is initialized to the peasant's last message sequence (not the thread tip)
- Test coverage confirms the fix works correctly

STATUS: DONE
