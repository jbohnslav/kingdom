---
from: peasant-kin-f6b0
to: king
timestamp: 2026-02-11T02:39:19Z
---

## What I did this iteration

1. **Root-caused the quality gate failures**: The harness's `run_tests()` uses `sys.executable` (the parent venv's Python), which imports `kingdom.harness` from the parent project's installed package — not the worktree's modified source. So my new test was running against the old, unfixed code and correctly failing.

2. **Fixed it**: Added `pythonpath = src` to `pytest.ini`. This tells pytest to prepend the worktree's `src/` directory to `sys.path`, ensuring that `import kingdom.harness` resolves to the worktree's code regardless of which Python executable runs the tests.

3. **Verified**: Ran the full test suite using both the parent's Python and the worktree's Python — all 385 tests pass in both cases. Ruff lint is clean.

4. **Committed**: `a57d209 fix: add pythonpath=src to pytest.ini for worktree test isolation`

## Commits for this ticket
- `31e93bc` — fix: initialize last_seen_seq from peasant's last message, not thread tip
- `a57d209` — fix: add pythonpath=src to pytest.ini for worktree test isolation

## Acceptance criteria met
- King messages sent while the peasant was down are no longer skipped
- `last_seen_seq` is initialized from the peasant's last message sequence (not the thread tip)
- Test coverage confirms the fix (`test_loop_picks_up_king_messages_sent_while_down`)
- Quality gates pass from both parent and worktree Python executables
- All 385 tests pass, lint clean

STATUS: DONE
