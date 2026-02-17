---
from: codex
to: king
timestamp: 2026-02-16T21:06:29Z
---

I’ll inspect ticket `7397` and the related context in the repo/`kd` data so I can give a concrete take on your proposed root cause. I’ll only read state and won’t modify files or git state.
I’m using the `kingdom` skill workflow here since this is a `kd` ticket discussion. Next I’m pulling the exact ticket text and nearby council/thread context before weighing in on the Cursor error cause.
I’ve pulled the full ticket history; the latest notes point to a poll/delete timing race as the primary Cursor issue. I’m now checking the current `app.py`/`poll.py` code paths to confirm whether that diagnosis matches implementation behavior.
I confirmed the key lifecycle code paths. I’ll now check the test that documents the fast-response race and whether it still fails or is now passing.
I found the exact regression test: `test_cursor_fast_response_stream_deleted_before_poll` currently expects thinking to be present even when the stream file is deleted pre-poll. I’ll run just that test to confirm current behavior rather than infer.
I also want to rule out double-deletion or retry behavior in `CouncilMember.query`, since that can affect stream visibility timing. I’m checking that call chain now.
`run_query` is indeed unlinking the stream in `finally`, and `query_once` writes incrementally with no retention buffer. I’m running a small focused test subset for the multi-round/ordering paths to verify those are stable and isolate Cursor to the deletion race.
Yes, if your suspected cause is the stream-file timing race, I agree.

What I verified:

- `ThreadPoller` only reads live `.stream-*.jsonl` files every 100ms (`src/kingdom/tui/app.py:174`, `src/kingdom/tui/poll.py:118`).
- `run_query()` unlinks the stream file immediately in `finally` (`src/kingdom/tui/app.py:363`).
- So for fast Cursor replies, thinking/text can be written and deleted before the next poll tick, which means no `ThinkingDelta` is ever emitted.

I also ran the targeted regression test and it currently fails exactly this way:
- `tests/test_tui_poll.py:1235` (`test_cursor_fast_response_stream_deleted_before_poll`)
- failure is `len(thinking) == 0` when the test expects `1`.

So this looks like a real root cause, not a parser-shape issue. One caveat: Cursor also legitimately emits no thinking on some turns, so even after fixing this race, thinking won’t appear 100% of the time.
