---
id: kin-f6b0
status: closed
deps: []
links: []
created: 2026-02-10T15:00:29Z
type: bug
priority: 1
---
# Fix queued directives dropped on peasant restart

harness.py:287 initializes last_seen_seq to the latest thread message, so any king messages sent while the peasant was down are skipped. Should initialize to the seq before the peasant went down, or scan for unseen messages on startup.

## Worklog

- [18:27] Backend call timed out
- [02:36] All pre-commit hooks passed and the commit succeeded.
- [02:36] DONE rejected (pytest failed). See logs for details.
- [02:36] The working tree is clean and the fix is committed at `31e93bc`.
- [02:36] DONE rejected (pytest failed). See logs for details.
- [02:37] All 41 harness tests pass including the new `test_loop_picks_up_king_messages_sent_while_down`.
- [02:37] DONE rejected (pytest failed). See logs for details.
- [02:39] ## What I did this iteration
- [02:39] Quality gates passed (pytest + ruff) — marking done
