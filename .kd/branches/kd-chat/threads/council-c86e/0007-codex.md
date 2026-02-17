---
from: codex
to: king
timestamp: 2026-02-16T23:53:52Z
---

Using the `kingdom` skill for this review. I’ll read `cf1a` and `tests/test_tui_integration.py`, then assess coverage, harness design, isolation, and near-term improvements with concrete references.
I’ve read the integration suite and ticket scope. I’m now checking marker/flag wiring and whether the assertions actually validate each scenario’s intended behavior end-to-end.
The suite passes end-to-end, but I spotted a potentially suspicious session-isolation assertion, so I’m doing a quick one-off reproduction to verify what behavior it’s actually proving.
**Findings**

1. `Scenario claims are stronger than assertions in several tests` (medium)
- Stream lifecycle claims `waiting -> streaming -> finalized`, but test only checks finalized message exists, not intermediate states or replacement correctness (`tests/test_tui_integration.py:301`).
- Error lifecycle does not verify timeout-specific labeling behavior, only that an `ErrorPanel` exists (`tests/test_tui_integration.py:333`).
- Escape interrupt scenario says interrupted state is rendered, but test only checks `terminate()` calls and flag (`tests/test_tui_integration.py:483`).
- Auto-turn follow-up test does not assert exact count/order/budget enforcement; it only waits for one extra claude file (`tests/test_tui_integration.py:546`).
- “Fresh thread isolation” scenario is actually “session_id cleared after query”; it does not assert cross-thread/new-thread non-inheritance against persisted session files (`tests/test_tui_integration.py:587`).

2. `Timing strategy partially contradicts ticket intent` (medium)
Ticket says bounded polling helper over fixed sleeps, but many tests still use hard pauses (`tests/test_tui_integration.py:223`, `tests/test_tui_integration.py:269`, `tests/test_tui_integration.py:373`, etc.). This can be flaky under load/CI variance.

3. `FakeMember harness is useful but under-exercises real parser paths` (low-medium)
`make_agent_config` hardcodes `backend="claude_code"` for all members (`tests/test_tui_integration.py:55`), so codex/cursor stream parsing branches are not covered.
Also FakeMember writes one-shot stream output (`tests/test_tui_integration.py:96`) rather than multi-delta progression, so streaming transition behavior is lightly tested.

4. `Potential cleanup fragility in no-op run_query patch` (low)
Using `asyncio.sleep(999)` as patched `run_query` (`tests/test_tui_integration.py:263`) can leave long-lived worker coroutines until teardown cancellation. Usually fine, but brittle if lifecycle behavior changes.

---

**Answers to your 4 questions**

1. Are 22 tests covering all 11 scenarios well?
Coverage breadth is good; depth is uneven. You hit all 11 headings, but scenarios 4/5/8/9/10 are only partially validated.

2. Is FakeMember/harness solid?
Solid for fast deterministic integration harnessing and file-poll flow. Main fragility is limited realism (single backend shape, single-delta stream, minimal process/session behavior).

3. Is test isolation adequate?
Yes overall. `tmp_path` + function-scoped fixtures isolate filesystem state well (`tests/test_tui_integration.py:131`). Marker/flag gating is correctly wired (`tests/conftest.py:14`, `pytest.ini:6`).

4. Improvements now vs defer
Worth doing now:
- Strengthen assertions for scenario-critical behaviors (stream transitions, timeout labeling, interrupted panel rendering, exact auto-turn budget/order, true fresh-thread isolation).
- Replace fixed sleeps with `wait_until` + explicit predicates.
- Add at least one backend-variant stream test (non-claude parser path).

Reasonable to defer:
- multi-size layout tests
- visual/snapshot diffing
- broad fuzz/property tests for chat timing permutations.
