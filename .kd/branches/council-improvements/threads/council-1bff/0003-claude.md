---
from: claude
to: king
timestamp: 2026-02-15T13:13:18Z
---



I'll review the diff and relevant source files to give you a thorough analysis.Now let me read the existing source files for additional context.Now let me check the retry command and how `*Error:` prefix detection works for the retry logic.Let me check the `mock_council_query_to_thread` helper — it has a bug I spotted.Now let me check one more thing about the stream file handling during retries:Good. I've read everything I need. Here's the review.

---

## Review: Ticket 6412 — Council Async UX Fixes

### 1. Correctness

**BUG: `mock_council_query_to_thread` not updated** (`tests/test_cli_council.py:46`)

The test helper still has the old inline logic:
```python
body = resp.text if resp.text else f"*Error: {resp.error}*"
```

The whole point of `thread_body()` was to centralize this. The mock should call `resp.thread_body()` instead. Right now it also can't produce the new `"*Empty response…"` format, meaning tests that check retry detection against empty responses would silently get the wrong thread body.

**BUG: Retry + streaming creates corrupt stream files**

When `query()` retries with a stream_path, it does:
1. `stream_path.unlink()` to clean up the failed attempt's stream file
2. Calls `query_once()` again which opens with `"a"` (append)

But the **watcher** (`read_stream_files`) is tracking byte offsets into the stream file. When the retry deletes the file and creates a new one, the watcher's `stream_positions[name]` still holds the old offset from the deleted file. On the next read it'll `seek(old_pos)` into the new (smaller) file. Python's `f.seek()` past EOF doesn't error — it returns empty. So the watcher just goes silent until the new file grows past the old offset.

In practice this means: during a retry, the live streaming preview freezes for that member until the new response exceeds the length of the failed one. Not catastrophic, but a real UX bug that undermines the streaming feature.

**Fix**: Reset stream positions when a stream file disappears. The code at line 844-846 detects deletion and discards from `streaming_members`, but doesn't reset `stream_positions[name]`. Add `stream_positions.pop(name, None)` there.

**Edge case: Retry timeout is per-attempt, not total**

With `max_retries=2` and a 600s timeout, worst case is 3 × 600s = 30 minutes for a single member. The other members in a parallel `query_to_thread` call will have finished long ago. Meanwhile the worker process stays alive, and the watcher's 300s default timeout will have expired. Not a bug per se, but worth documenting or considering a total timeout cap.

### 2. Design

**Retry strategy: sound overall.** The escalation from same-session → reset-session is the right idea. Transient API errors often resolve on retry; corrupted session state resolves on reset. The non-retriable prefix check is a good guard.

**Concern: retry hides timeouts.** A timeout error doesn't match `NON_RETRIABLE_PREFIXES`, so timeouts get retried. If a model consistently takes >600s, you'll wait 1800s (3 attempts × 600s) before giving up. Timeouts should probably be non-retriable, or at least only retry once (not with session reset — a fresh session is *more* likely to timeout since it loses context).

**`thread_body()` centralization: clean.** Four call sites collapsed into one method. The empty-response sentinel is a good addition. However, `thread_body()` returns `"*Error: …*"` with markdown italics — this is a format that `council_retry` does string-prefix matching against (`msg.body.startswith("*Error:")`). This coupling between the serialization format and the retry detection logic is fragile. If someone changes `thread_body()` to use a different format (e.g., `> **Error:**`), retry silently breaks. Consider a more robust marker — a metadata field in the message, or a dedicated helper like `is_error_response(body)`.

**`council retry` prompt extraction is brittle.** It takes `last_king_msg.body` as the prompt, but `body` includes the COUNCIL_PREAMBLE, phase prompt, and agent prompt baked in by `build_command()`. Wait — actually no, looking at the thread creation flow, the king message body is the user's original prompt, not the full prompt. That's fine. But worth verifying that `council ask` always stores the raw user prompt, not the assembled prompt, in the thread.

### 3. UX — Streaming Watch

**The approach is good.** Tailing `.stream-{member}.jsonl` and showing a char-count + 60-char preview is a meaningful improvement over a bare spinner. Users can see that something is happening.

**Suggestions:**
- The 60-char preview with newlines flattened to spaces can produce garbled output (half a markdown heading, partial code). Consider showing just the char count + a "streaming..." indicator, or word-boundary truncation.
- `refresh_per_second=4` with `time.sleep(0.25)` means the live display updates at most ~4 times/sec. Fine for a terminal, but the tight loop of `read_stream_files()` + `list_messages()` on every iteration means you're hitting the filesystem 4×/sec per member. For 3 members that's 12+ file reads/sec. Harmless on local disk, but worth noting.

### 4. Test Coverage

**What's tested well:**
- `thread_body()` — all three branches (text, error, empty)
- Retry — success, non-retriable errors, escalation to session reset, max_retries=0
- CLI: reset single member, unknown member, retry with no thread / all ok / failed / missing

**What's missing:**

1. **No test for retry with timeouts.** A timeout is the most common real failure. Does the retry correctly handle a `TimeoutExpired` → retry → success flow? The `query_once` `TimeoutExpired` handler returns an `AgentResponse` with `error="Timeout after {timeout}s"` — this doesn't match `NON_RETRIABLE_PREFIXES`, so it *will* retry. But there's no test confirming this path works or that the stream file gets cleaned up properly between attempts.

2. **No test for the streaming watch.** `watch_thread` is the most complex function in this diff and has zero test coverage. The `read_stream_files` / `build_status_display` / Live interaction is all untested. I understand it's hard to test Rich Live displays, but you could at least test `read_stream_files` as a standalone function — extract it and unit test the byte-offset tracking.

3. **No test for `query_to_thread` retry interaction.** When `query_to_thread` calls `member.query()` (which now retries internally), and the stream file is being deleted/recreated during retries while the watcher reads it — this concurrent scenario has no test.

4. **`mock_council_query_to_thread` doesn't use `thread_body()`.** As noted above — the test helper has stale logic.

### 5. Changes I'd Make Before Merging

**Must fix:**
1. Update `mock_council_query_to_thread` to use `resp.thread_body()` — consistency bug
2. Reset `stream_positions` when stream file disappears in `read_stream_files()` — streaming UX bug during retries
3. Make timeouts non-retriable (or single-retry, no session reset) — 1800s worst-case is unacceptable

**Should fix:**
4. Add `is_error_response(body: str) -> bool` helper instead of raw `startswith("*Error:")` checks in `council_retry` — fragile coupling
5. Add a test for retry-after-timeout

**Nice to have:**
6. Extract `read_stream_files` to a testable function (takes positions dict, returns updated state)
7. Document the total-timeout implications of per-attempt retry in the docstring
