---
id: "8fda"
status: closed
deps: []
links: []
created: 2026-02-21T18:40:34Z
type: bug
priority: 2
---
# Cancel stale run_query tasks when user sends a new message

When `send_message` is called while a member is still responding, `remove_member_panels` clears the UI widgets but the old `run_query` coroutine keeps running. It finishes, writes to the thread via `add_message`, and the poller renders it as a stale response alongside the new one.

Two locations need guards:

1. **`send_message` (`app.py:~592`)** — The old `run_query` task per member must be cancelled (or its results ignored) before launching a new one. Options: track worker tasks per member and cancel them, or pass a generation number into `run_query` and bail before `add_message` if stale.

2. **`run_chat_round` broadcast (`app.py:~671`)** — The initial `asyncio.gather` has no generation check. If the user sends a second message while the first broadcast is in flight, both complete and write to the thread. Add a generation guard after the gather returns.

Both stem from the same root cause: worker tasks aren't cancelled/invalidated when a new message supersedes them.

Flagged by both Codex and Claude bot reviews on PR #26.

## Acceptance Criteria

- [x] Sending a new message while a member is responding cancels or invalidates the old run
- [x] The `asyncio.gather` broadcast in `run_chat_round` checks generation before writing results
- [x] No stale responses appear in the chat after re-sending

## Worklog

Added `generation` parameter to `run_query`. When passed, the response is
discarded if `self.generation` has moved on before `add_message` is called.

Changes in `app.py`:
- `run_query` accepts optional `generation` param; checks after query returns
- `run_chat_round` passes `generation` to all `run_query` calls (broadcast, sequential, auto-turns)
- `run_chat_round` checks generation after `asyncio.gather` returns, bails if stale
- `send_message` passes `gen` to directed (single-target) `run_query` calls

Tests in `test_tui.py`:
- `test_run_query_skips_persist_when_generation_stale` — generation bumped mid-query, response discarded
- `test_run_query_persists_when_generation_matches` — generation stable, response persisted
- `test_broadcast_gather_discards_stale_results` — generation bumped during gather, no messages written
