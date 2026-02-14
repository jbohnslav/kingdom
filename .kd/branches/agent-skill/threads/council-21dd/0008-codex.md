---
from: codex
to: king
timestamp: 2026-02-14T02:11:02Z
---

I’ll review the unstaged working tree as a code review: inspect `git status` and diffs, then report concrete findings by severity with file/line references and any testing gaps.
I’ve pulled the diffs; next I’m checking the exact line context to validate behavior and produce precise review findings with file/line references.
I’m now tracing how `.stream-*.md` files are consumed so I can verify whether this implementation is functionally correct end-to-end or has integration gaps.
I’m checking `agent.parse_response` to verify whether returning raw partial stdout on timeout is compatible with existing parsing semantics or introduces regressions.
I found likely regressions in `CouncilMember.query`; I’ll run targeted council tests to confirm actual breakages before finalizing the review findings.
Test execution is exposing multiple failures and appears to hang in one path, which aligns with the timeout/IO concerns in the new `Popen` loop. I’m collecting full failure details next.
I confirmed at least one concrete regression: existing `CouncilMember.query` tests now fail because the implementation bypasses the prior `subprocess.run` path. I’ll inspect the failing test block to separate test-only breakage from real runtime issues.
I verified one concrete runtime bug (timeout isn’t enforced with partial lines). I’m doing one more quick reproduction to see if the loop can also drop trailing output lines after process exit.
1. **High: Timeout is not actually enforced when output is partial-line buffered.**
`readline()` can block past the configured timeout, so the timeout check is skipped while blocked.
Refs: `src/kingdom/council/base.py:85`, `src/kingdom/council/base.py:86`, `src/kingdom/council/base.py:116`
Evidence: I reproduced with `timeout=1` and a child process that writes one byte without newline then sleeps 2s; wall time was ~2.02s, not 1s.

2. **High: Timeout can be bypassed entirely if child closes stdout/stderr early.**
When both pipes are closed, loop exits (`if not reads: break`) and then `process.wait()` has no timeout. This can wait arbitrarily long and still return success (`error=None`).
Refs: `src/kingdom/council/base.py:96`, `src/kingdom/council/base.py:97`, `src/kingdom/council/base.py:133`, `src/kingdom/council/base.py:144`
Evidence: I reproduced with `timeout=1` and child closing FDs then sleeping 3s; wall time was ~3.02s and response had no timeout error.

3. **Medium: Existing council unit tests are broken and now execute real agent CLIs.**
The implementation switched from `subprocess.run` to `subprocess.Popen`, but tests still patch `subprocess.run`, so mocks are bypassed. This makes tests flaky, slow, and potentially side-effectful (real API/tool calls).
Refs: `src/kingdom/council/base.py:72`, `tests/test_council.py:156`, `tests/test_council.py:172`, `tests/test_council.py:191`
Evidence: `source .venv/bin/activate && pytest tests/test_council.py -k "test_query_passes_stdin_devnull or test_query_returns_agent_response or test_query_updates_session_id" -vv` failed 3/3, and one test observed a real model response.

4. **Low: Default timeout behavior changed globally from 300s to 600s.**
May be intended, but it doubles wait time before failure and can affect UX/tests/docs.
Refs: `src/kingdom/cli.py:285`, `src/kingdom/council/council.py:21`, `src/kingdom/council/worker.py:31`

Open question:
- Is 600s the intended new product default, or should the previous 300s remain and only streaming internals change?

No files were modified during this review.
