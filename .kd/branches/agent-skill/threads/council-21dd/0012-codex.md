---
from: codex
to: king
timestamp: 2026-02-14T02:25:00Z
---

I’ll re-check the current `git diff` and then audit `base.py` execution flow plus related tests to give a correctness-focused review with concrete edge cases and line references.
I’m running the council test file as-is to confirm whether the new Popen mocks actually protect against real CLI execution and to catch any remaining regressions.
I confirmed the updated tests now pass, and I’ve validated timeout behavior manually. I’m doing one final pass on edge-case paths (join/cleanup behavior and stream-file lifecycle) before summarizing findings.
1. **Medium: potential partial-output truncation/race due fixed `join()` timeouts on reader threads.**
`query()` proceeds after `out_thread.join(timeout=5)` / `err_thread.join(timeout=5)` (and `2s` on timeout path), then closes `stream_file` in `finally`. If a reader thread is still alive, output can be truncated and thread writes can race a closed file.
Refs: `src/kingdom/council/base.py:116`, `src/kingdom/council/base.py:117`, `src/kingdom/council/base.py:146`, `src/kingdom/council/base.py:147`, `src/kingdom/council/base.py:189`

2. **Medium: test mocking pattern hides the core polling/timeout behavior.**
`mock_popen()` sets `proc.poll.return_value` to a final code immediately, so the `while process.poll() is None` loop is effectively skipped in most tests. That means timeout/kill/drain behavior is largely untested even though that’s where correctness risk is.
Refs: `tests/test_council.py:25`, `tests/test_council.py:31`, `src/kingdom/council/base.py:108`

3. **Low: timeout-path coverage regression in `tests/test_council.py`.**
The previous explicit timeout test for `query()` is gone; current tests assert happy-path parsing and stderr handling but not `process.kill()`/partial-output behavior under timeout.
Refs: `tests/test_council.py:156`, `tests/test_council.py:196`, `src/kingdom/council/base.py:109`, `src/kingdom/council/base.py:141`

4. **Low: stream files are written/cleaned, but no watcher currently consumes them.**
`query_to_thread()`/worker create `.stream-*.md` and delete on completion, but `watch` logic still renders only thread messages; this leaves edge cases where crashes can strand `.stream-*` files without functional benefit.
Refs: `src/kingdom/council/council.py:108`, `src/kingdom/council/council.py:125`, `src/kingdom/council/worker.py:52`, `src/kingdom/council/worker.py:58`, `src/kingdom/cli.py:661`

Quick validation notes:
- I ran `tests/test_council.py` and `tests/test_cli_council.py`; both pass.
- Manual runtime checks indicate timeout enforcement is improved versus the earlier `select/readline` version (partial-line and closed-fd cases now time out correctly).
