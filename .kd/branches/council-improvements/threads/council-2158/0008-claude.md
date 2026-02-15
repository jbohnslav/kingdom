---
from: claude
to: king
timestamp: 2026-02-15T18:32:17Z
---



Let me do a thorough review. I'll start by reading the design doc and tickets, then dig into the code.Let me now read the key implementation files and verify each design requirement.Good. Now let me run the CLI commands and tests as integration checks.Good. Now let me run the test suite and check some edge cases in the code.All 640 tests pass. Now let me check a few specific code quality items and the mock inconsistency I flagged in the prior review.Good — the mock was already updated to use `resp.thread_body()`, and `is_error_response()` exists as a proper helper. Both issues from my earlier review have been addressed. Let me check a few more things.Now let me check if the watch_thread `stream_positions` reset issue was fixed.Good — that backlog ticket exists and is well-specified. Let me now check the `council retry` targeting logic (the `last_king_msg.to` handling that was mentioned in the explore output) and verify the `council show` fallback behavior.Now let me check the `council show` fallback to most recent thread and the `--all` flag.Now let me verify the `thread_response_status` logic handles the edge case where `is_error_response` and the inline check stay in sync.There's the issue — `thread_response_status()` in `thread.py` has its own inline error detection logic (lines 396-398) that doesn't use `is_error_response()` from `cli.py`. The logic is duplicated. Let me confirm they're consistent.Let me also check if there's a `--watch` flag or auto-watch behavior on `council ask`.Good. I can see that the default sync path (line 499+) now uses `query_to_thread` with a callback for multi-member queries, which does write stream files. Only the single-member `--to` path still uses the old spinner. That's actually fine — single-member queries are fast enough that live streaming isn't critical.

Let me check one more thing — whether `is_error_response` should be in `thread.py` rather than `cli.py`, since `thread_response_status` needs the same logic.Let me verify each closed ticket's acceptance criteria against the implementation.Now let me check the one ticket that's still **open** — 6412. The worklog shows it was reopened after validation.Let me check 6412's actual status — it says "open" in `kd tk show` but "closed" in `kd tk list --include-closed`.OK, I misread earlier — it actually says `[open]`, not `[closed]`. So 6412 is correctly open. Let me also verify e756's actual status since 6412 depends on it.Good. Now let me also check the `e756` acceptance criteria — its checkboxes aren't checked in the file but it's marked closed.OK — all the checkboxes are unchecked in the file, which is a minor hygiene nit (status: closed but ACs not ticked). Not a real issue — the worklog lives in the `kd tk show` formatted output.

Now let me verify the one thing I haven't checked — whether `council ask` (sync, multi-member, non-JSON) actually uses the streaming path now.

Looking at `cli.py:516-521`:
```python
else:
    def on_response(name, response):
        render_response(response, console)
    c.query_to_thread(prompt, base, feature, thread_id, callback=on_response)
```

This calls `query_to_thread` which writes stream files. Good — the sync multi-member path does use streaming. The only path that doesn't is single-member `--to` (which uses a bare spinner). That's reasonable.---

## Full Review: council-improvements branch

### Summary

This branch delivers Phase 0 + Phase 1 of the design doc. 14 tickets closed, 1 (6412) intentionally left open. The implementation is solid, well-tested (640 tests, all green), and the CLI commands work correctly in practice. All the issues I flagged in the earlier 6412 review have been addressed.

### Design Alignment

**What's delivered (matches design):**
- Phase 0: stream-json mode, NDJSON parsers, stream-line extractors (e756)
- Phase 1: error handling + retry (6412), richer status (a9c9), show pagination (70f6/d09d), list enrichment (a4f5), per-member reset, stream display in watch
- Plus housekeeping: configurable members (549b), ticket UX (4b4d, 6c9f, 748c, 2670, 4e21), style fix (41fb)

**What's deferred (correctly):**
- Auto-commit threads (1e3d) — in backlog, depends on e756 ✓
- `kd chat` TUI (Phase 2) — not in scope for this PR
- Group chat (Phase 3) — not in scope for this PR
- Message frontmatter metadata (9124) — backlog ticket exists

**Nothing missing from Phase 1 scope** except auto-commit (1e3d), which the design lists as Phase 1 but was moved to backlog. That's a reasonable deferral — it's a nice-to-have, not a UX fix.

### Ticket Status

All ticket statuses are correct:
- **6412 (open)**: Correctly open. The worklog documents why — timeout-partial responses aren't reliably detectable by retry/status. Backlog ticket 9124 tracks the proper fix. The question is: can this be closed as "good enough for now" or does it block the PR?
- **e756 (closed)**: All ACs met in code, just checkboxes not ticked in the file (cosmetic).
- **All other 12 tickets (closed)**: ACs verified against implementation, all met.

**Recommendation on 6412**: Close it. The core promise — meaningful errors, auto-retry, per-member reset, retry command, streaming watch — is fully delivered. The timeout-partial edge case is documented, has a backlog ticket (9124), and the code has an explicit comment explaining the tradeoff. Keeping it open blocks `kd done`.

### Code Quality

**Good:**
- `thread_body()` centralization eliminated 4 duplicate inline patterns
- `is_error_response()` helper in cli.py consolidates the error-detection string matching
- Retry strategy is well-structured: query() → query_once() split, non-retriable prefixes, logged retries
- Stream file handling in `read_stream_files()` is robust: handles deletion (line 996-999), file recreation/truncation (lines 1007-1011), OSError on stat and read
- `thread_response_status()` cleanly maps member states from concrete signals
- Config loading in watch_thread is wrapped in try/except (line 928-936) — bad config doesn't break watching

**Issues found:**

1. **Duplicated error-detection logic** — `is_error_response()` lives in `cli.py` (line 1088), but `thread_response_status()` in `thread.py` (lines 396-398) reimplements the same prefix checks inline. If the error format changes, you have to update both. `is_error_response` should live in `thread.py` next to `thread_response_status` and be imported by `cli.py`. **Backlog-worthy.**

2. **e756 acceptance criteria checkboxes unchecked** — The ticket is closed but none of the `- [ ]` items are ticked to `- [x]`. Pure cosmetic, no worklog either. Not a blocker.

3. **`council ask --to <member>` sync path doesn't use streaming** — Uses bare `Progress` spinner + `member.query()` (line 504-514). Works fine for single-member queries. The design doc's "should council ask always use stream-json" question (line 152) leans yes, but this only affects the display path, not the underlying query (which already uses stream-json via `build_command(streaming=True)`). The stream file is written by `query_once` but nobody tails it in this code path. **Not a bug, just a lesser UX path.**

4. **`splitlines()` partial-line risk in `read_stream_files()`** — If `f.read()` catches a line mid-write (the agent process is still writing), the last element from `splitlines()` could be a partial JSON line. `extract_stream_text()` calls `json.loads()` which will fail, returning `None` — so it's handled gracefully. But the byte offset advances past this partial line, so it's silently lost. In practice this is unlikely (the agent flushes after each line) and the impact is one missing text fragment in the streaming preview. **Not worth fixing.**

### Edge Cases

- **Retry after `council ask --to claude`**: The `to` field in the king message is `"claude"`, not `"all"`. The retry command's logic at line 1139-1143 correctly handles this — it parses the `to` field and only expects `claude`, not all members. Good.
- **Multiple @mentions**: `council ask @claude @codex "question"` filters council to just those two members (line 396). If one fails, retry correctly scopes to only the failed subset. Good.
- **Thread with no king message**: Both `watch_thread` and `council_retry` handle this with explicit error messages. Good.
- **Empty thread**: `council_show` catches it at line 627-629. Good.

### Recommendations

1. **Close 6412.** The work is done. The timeout-partial edge case is documented and tracked in 9124.
2. **File a backlog ticket** for moving `is_error_response()` to `thread.py` and having `thread_response_status()` use it. Prevents divergence.
3. **Branch is ready for PR** once 6412 is closed and `kd done` passes.
