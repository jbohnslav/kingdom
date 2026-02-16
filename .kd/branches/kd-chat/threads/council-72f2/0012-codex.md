---
from: codex
to: king
timestamp: 2026-02-16T14:13:36Z
---

Using the `kingdom` skill for this review. I’ll inspect the five files you listed plus the `3b76` ticket/design context, then report findings by severity with concrete file references.
I’ve pulled ticket context and config/council changes. Next I’m reading `tui/app.py` and the new tests in detail to look for correctness gaps and race conditions against those acceptance criteria.
I need one more pass over the lower half of `tests/test_tui.py` and related prompt/history code to verify whether important behaviors are untested or silently broken.
I’ve identified a few likely race/behavioral risks by inspection; I’m running the relevant test slices now to confirm what’s covered vs untested before I finalize findings.
**Findings (highest severity first)**

1. High: generation preemption can run the same member concurrently (race + stream collision).
`send_message()` always launches a new worker immediately (`src/kingdom/tui/app.py:314`) after bumping generation (`src/kingdom/tui/app.py:287`), while older workers are not canceled. In broadcast mode, `run_chat_round()` enters `asyncio.gather(...)` without a generation guard (`src/kingdom/tui/app.py:375`, `src/kingdom/tui/app.py:383`). That allows overlapping queries to the same member and shared `.stream-{member}.jsonl` paths (`src/kingdom/tui/app.py:381`).
I reproduced this with a one-off async script: both members reached `max_active=2` (same member queried concurrently).

2. Medium-high: waiting panel mount can duplicate IDs under fast turns.
Auto-turn mounts `WaitingPanel(id=f"wait-{name}")` each turn (`src/kingdom/tui/app.py:406`), but prior wait/stream panels are only removed when poll events are processed (`src/kingdom/tui/app.py:532`). If rounds advance faster than poll replacement, duplicate ID mount errors are possible.

3. Medium: sequential mode round counting is ambiguous and likely off-by-one vs intent.
Implementation does one initial sequential pass (`src/kingdom/tui/app.py:385`) plus `auto_rounds` additional rounds (`src/kingdom/tui/app.py:396`). Tests lock this behavior (`tests/test_tui.py:1197`). If `auto_rounds` means total rounds without user input, current behavior overshoots by one in sequential mode.

4. Medium: tests miss key runtime races.
Auto-turn tests mock DOM operations (`tests/test_tui.py:1024`), so they won’t catch real Textual duplicate-ID behavior or send-time concurrent-generation overlap.

5. Low: spec drift on `auto_rounds`.
Code allows `0` (`src/kingdom/config.py:197`), tests reflect this, but design text still says positive (>0). This should be explicitly reconciled.

**Assessment of your 5 design decisions**

- Single coordinator coroutine: good direction for ordering and clearer control flow.
- Generation counter: good idea, but incomplete without preventing overlap at send/phase-start boundaries.
- Directed messages skip auto-turns: correct for single-target directed asks.
- Waiting panels inside coordinator: good UX intent, needs idempotent/replace-safe mounting.
- `auto_rounds=0`: good and practical; keep it, but align docs.

**Recommendation**

Keep ticket `3b76` open until concurrency/preemption semantics are tightened.
At minimum, decide one policy explicitly and test it end-to-end: either queue new sends until current generation reaches a safe boundary, or hard-cancel old generation before launching the new one. Then add a real mounted Textual test for panel lifecycle under fast responses.
