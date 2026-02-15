---
from: codex
to: king
timestamp: 2026-02-15T13:16:42Z
---

I’ll review `/tmp/6412-review.diff` as a code review only, focusing on correctness, retry/error design, UX flow, and coverage gaps. I’m first loading the `kingdom` skill instructions and the diff content, then I’ll drill into risk points with concrete file/line references.
I’ve loaded the relevant skill and the first part of the patch. Next I’m reading the rest of the diff and then I’ll validate behavior against existing council/thread code for hidden edge cases.
I have the full patch now. I’m checking surrounding implementations (`watch`, message parsing, agent response parsing, and status commands) to verify whether the new retry/error heuristics and stream handling align with existing behavior or create false positives.
I’m now validating the tests and helper mocks to see whether they actually exercise the risky paths (especially async/watch streaming and retry classification), and to spot untested regressions.
I’ve identified a few likely logic risks already; I’m running focused tests next to confirm what the current suite does and, more importantly, what it does not exercise.
`uv run` is failing in this sandbox (cache/init panic), so I’m switching to the project venv directly to run targeted pytest checks and still validate coverage gaps.
I’ve narrowed this to a handful of concrete issues; I’m grabbing exact line numbers now so the review is actionable and severity-ranked rather than generic commentary.
I’m quickly validating two suspected logic bugs with isolated CLI reproductions (no repo changes) so the review can distinguish confirmed issues from theoretical ones.
Two core bugs are now confirmed with repros. I’ll validate one more streaming edge case (file rotation during retries) and then provide the final severity-ranked review.
Used `kingdom` skill context for council workflow semantics.

**Findings (ordered by severity)**
1. **High: `council retry` can retry the wrong members after targeted asks.**
`council_retry` derives `expected` from thread metadata (`src/kingdom/cli.py:953`), not from the most recent king message target. In a thread originally created with all members, if the latest ask was `--to codex`, retry still treats `claude`/`cursor` as missing and re-queries them. I confirmed this with an isolated CLI repro: retry targeted `claude,cursor` even though only `codex` was asked.

2. **High: retry success/failure detection is brittle and misses real failures.**
Failure detection is string-prefix based (`src/kingdom/cli.py:968`), while thread storage prefers text over error (`src/kingdom/council/base.py:26`, `src/kingdom/council/base.py:209`). A timeout with partial text is persisted as plain text, so retry treats it as successful and does nothing. I confirmed this repro: `kd council retry` returned “Nothing to retry” for a partial timed-out response case.

3. **Medium: streaming watch can stop showing stream text after internal retry.**
`CouncilMember.query()` deletes and recreates `.stream-*` between attempts (`src/kingdom/council/base.py:117`, `src/kingdom/council/base.py:125`), but watcher keeps old byte offsets when file disappears (`src/kingdom/cli.py:843`, `src/kingdom/cli.py:851`). On recreated shorter files, `seek(old_pos)` can sit past EOF, so no new stream text is read. Final response still appears, but live streaming UX breaks in retry scenarios.

4. **Medium: `council watch` now depends on full config validity and can crash on unrelated agent defs.**
Watch resolves all agents (`src/kingdom/cli.py:778`), so a bad backend in any configured agent can make watch fail before reading thread messages, even if that agent is not in the thread. I confirmed repro: invalid extra backend caused exit code 1 with `ValueError`.

**Retry strategy design**
The 3-step strategy (try, retry same session, retry with reset) is directionally sound. The weak point is **classification**: relying on rendered markdown bodies (`*Error:` prefixes) is not robust enough for correctness.

**Streaming UX assessment**
The live tail approach is a good UX direction for async council, but it needs stronger file-rotation handling and graceful fallback (if stream parsing/config lookup fails, keep polling finalized messages rather than failing).

**Test coverage gaps**
1. Missing test for `retry` after targeted ask (`--to`) in existing multi-member thread (`tests/test_cli_council.py:846`).
2. Missing test for partial-timeout response classification (text + error) causing false “success” in retry logic (`tests/test_cli_council.py:846`, `tests/test_council.py:209`).
3. No tests for `watch_thread` streaming behavior, including stream file delete/recreate and offset reset (`tests/` has no watch tests).
4. Missing test that `council watch` handles unrelated invalid agent config without crashing.

**Before merging, I’d change**
1. Compute retry candidates from structured round state (or message metadata), not markdown body prefixes.
2. Derive expected members for retry from the latest ask target semantics, not static thread member list.
3. Reset stream offset state when `.stream-*` disappears/reappears.
4. Make watch resilient to config/backend resolution failures (best-effort streaming, still show final messages).
