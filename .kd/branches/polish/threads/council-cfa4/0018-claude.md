---
from: claude
to: king
timestamp: 2026-02-17T03:53:17Z
---



Good question. Let me analyze the actual commits to give you a concrete recommendation.Those don't look like cursor-removal commits. Let me find the actual ones.Found it — `3778bbb` is the nuclear removal commit. Let me examine it closely.That commit only touched a ticket file. The actual code removal must be elsewhere. Let me look more carefully.The ticket closure at `3778bbb` only touched the ticket file. The actual cursor code removal happened earlier. Let me find where `parse_cursor_response` and other cursor functions were actually deleted.So the cursor removal happened inside commit `4e7c196` ("feat(chat): Ctrl+T thinking visibility toggle hotkey"). That's a squash merge that bundled unrelated changes together. Let me see the full scope.Yep — `4e7c196` is a big squash merge that bundled the cursor removal with a bunch of other work. It's the only commit that matters (the other two SHAs you mentioned were unrelated). Let me look at exactly what was removed from the key files.Now let me check what other changes happened in that commit to `test_tui_poll.py` and `poll.py`, and check the current state of the files.Now let me also check what changes happened to `harness.py` and `council/worker.py`:Good — `harness.py` and `council/worker.py` changes are unrelated to cursor (worklog timestamps and Rich formatting). Now let me check the current state of agent.py to see what's already been modified:So you've already started restoring some of it manually. Now I have the full picture. Here's my analysis:

---

## Situation

Everything was removed in a single squash commit (`4e7c196`), not three. That commit also contains ~30 other unrelated changes (Ctrl+T toggle, ticket moves, harness timestamps, widget updates, etc.), making `git revert` completely impractical.

## Recommendation: Option 3 — Selective patch extraction

This is the cleanest approach. Here's the exact strategy:

### Step 1: Generate a reverse diff of only the cursor deletions

```bash
git diff 4e7c196 4e7c196^ -- src/kingdom/agent.py > /tmp/restore-agent.patch
git diff 4e7c196 4e7c196^ -- tests/test_tui_poll.py > /tmp/restore-tui-poll.patch
```

This gives you "what was removed" as additions. You then review each patch and apply selectively.

### Step 2: For each file, apply only the hunks you want

**`src/kingdom/agent.py`** — Apply the full reverse patch. Every deletion was cursor backend code you want back (parsers, builders, extractors, dict entries). You've already started this manually.

**`src/kingdom/config.py`** — Only restore `"cursor"` to `VALID_BACKENDS`. Do NOT restore cursor in `DEFAULT_AGENTS` or the comment. This is a 1-line manual edit — no patch needed.

**`tests/test_tui_poll.py`** — Apply most of the reverse patch, BUT skip:
- The `merge_assistant_snapshots` import restoration (it was removed from poll.py and should stay gone)
- The `TestMergeAssistantSnapshots` class (merge logic is removed)
- The `TestCursorCrossBatchSnapshot` class (depends on merge logic)
- The cursor-branching tests in `test_cursor_assistant_snapshot_chunks_should_use_latest_snapshot` (depends on merge logic)
- Keep all other cursor tests: thinking extraction, thinking accumulation, thinking cleared on finalization/retry, thinking-before-stream ordering

**`tests/test_config.py`** — Do NOT apply the reverse patch. All config test changes are correct as-is. Cursor should stay out of `DEFAULT_AGENTS` and default council members.

**`tests/test_cli.py`** — Do NOT restore cursor references. Cursor is not in DEFAULT_AGENTS, so `kd doctor` won't check it.

**`src/kingdom/tui/poll.py`** — Do NOT restore cursor branching in `poll()` or `tail_stream_file()`. The unified concat path is correct.

### Step 3: Verify

Run `pytest` to make sure all cursor backend tests pass and nothing else broke.

## Why not the other options?

| Option | Problem |
|--------|---------|
| `git revert` | Impossible — the commit has 30+ unrelated changes. Reverting it would undo Ctrl+T toggle, harness timestamps, widget changes, etc. |
| `git checkout <sha> -- <files>` | Too coarse — checking out the pre-removal version of agent.py would lose ALL post-removal changes to that file (there may be none, but it's a risky pattern for test files that have new tests added since) |
| Manual edit only | Error-prone for the large functions. Easy to miss a line in `parse_cursor_response` (95 lines) or `build_cursor_command` (40 lines) |

## Exact file-level decision matrix

| File | Action | Rationale |
|------|--------|-----------|
| `src/kingdom/agent.py` | Full reverse patch | All removals were backend code to restore |
| `src/kingdom/config.py` | Manual 1-line edit | Only `VALID_BACKENDS` needs cursor back |
| `src/kingdom/tui/poll.py` | No change | Unified concat path is correct |
| `tests/test_tui_poll.py` | Selective reverse patch | Restore thinking/stream tests, skip merge_snapshot tests |
| `tests/test_config.py` | No change | Correctly reflects cursor out of defaults |
| `tests/test_cli.py` | No change | Doctor only checks DEFAULT_AGENTS |

## One thing to watch

The cursor tests in `test_tui_poll.py` that use `cursor_thinking_event()` and `cursor_assistant_event()` helper functions — those helpers are still in the file (they weren't deleted, just the tests that called them were). So restoring the tests should work without any helper recreation. Let me verify:**Important finding**: The cursor helper functions (`cursor_assistant_event`, `cursor_thinking_event`, etc.) were *also* deleted — they're not in the current file. The commit deleted both the helpers and the tests. But the reverse diff I showed earlier didn't surface them because they were in a different hunk. Let me confirm:Now I have the complete picture. Let me also check whether there are further cursor tests later in the file that *survived* the removal:Interesting — there's **zero** cursor content remaining in `test_tui_poll.py`. The entire class `TestCursorSnapshotEdgeCases`, `TestRealCursorLongResponseWithToolCalls`, and all cursor helpers are gone. Let me check what the full removal scope was:There's a **second commit** (`d71d7fb`) that also removed massive chunks from `test_tui_poll.py` (556 lines deleted!). Let me see what it did:So commit `d71d7fb` removed even *more* cursor test infrastructure — the helper functions, `TestCursorSnapshotEdgeCases`, `TestRealCursorShortResponse`, `TestRealCursorEmptyResponse`, `TestRealCursorLongResponseWithToolCalls`, and all the cursor event helpers. And it also removed `merge_assistant_snapshots` from `poll.py`:Okay, now I have the **complete picture**. There are actually **two commits** that performed the removal:

1. **`4e7c196`** — Removed cursor from `agent.py` (backend dict, parsers, builders, extractors), `config.py` (DEFAULT_AGENTS, VALID_BACKENDS), `poll.py` (cursor branching), and some cursor tests from `test_tui_poll.py`
2. **`d71d7fb`** — Removed `merge_assistant_snapshots` from `poll.py`, and wiped all remaining cursor test infrastructure from `test_tui_poll.py` (helpers, edge case classes, real-response integration tests)

---

## Revised Recommendation

Given the two-commit scope and the complexity of what was deleted, here's my updated recommendation:

### Best approach: Hybrid (Option 3 + Option 4)

**For `src/kingdom/agent.py`**: Use `git checkout` from the pre-removal state. This is safe because the only changes to agent.py across both commits were pure cursor deletions — no other logic changed.

```bash
git checkout 4e7c196^ -- src/kingdom/agent.py
```

This restores the full file to pre-removal state. You already started manual edits, but this will be cleaner and guaranteed complete. Since the file had no other changes in those commits (harness.py, cli.py, etc. were separate hunks), this is risk-free.

**For `src/kingdom/config.py`**: Manual 1-line edit only. Add `"cursor"` back to `VALID_BACKENDS`. Do NOT restore it in `DEFAULT_AGENTS` or default council members.

**For `tests/test_tui_poll.py`**: This is the tricky one. You need to extract from **two different commits**. Use patch extraction:

```bash
# Get what 4e7c196 removed
git diff 4e7c196 4e7c196^ -- tests/test_tui_poll.py > /tmp/poll-tests-1.patch

# Get what d71d7fb removed
git diff d71d7fb d71d7fb^ -- tests/test_tui_poll.py > /tmp/poll-tests-2.patch
```

Then review each patch and apply hunks selectively. From `4e7c196`, restore:
- Cursor thinking tests (6 test methods)
- Thinking-before-stream ordering test

Skip from `4e7c196`:
- `merge_assistant_snapshots` import (function won't exist)
- `TestMergeAssistantSnapshots` class
- `TestCursorCrossBatchSnapshot` class
- `test_cursor_assistant_snapshot_chunks_should_use_latest_snapshot`

From `d71d7fb`, restore:
- All cursor helper functions (`cursor_assistant_event`, `cursor_thinking_event`, `cursor_system_init`, `cursor_user_event`, `cursor_thinking_completed`, `cursor_result_event`, `cursor_tool_call_event`)
- `TestCursorSnapshotEdgeCases`
- `TestRealCursorShortResponse`
- `TestRealCursorEmptyResponse`
- `TestRealCursorLongResponseWithToolCalls`

BUT these test classes reference `merge_assistant_snapshots` behavior. You'll need to update tests that depend on merge semantics to use simple concatenation instead. Specifically:
- `test_cursor_assistant_snapshot_chunks_should_use_latest_snapshot` — skip (tested merge behavior)
- `test_real_cursor_assistant_fragments_not_cumulative` — the pre-removal version uses `merge_assistant_snapshots` logic; update to use concat semantics
- `test_cursor_cross_batch_fragments` — same issue
- `test_cursor_fragments_without_final_snapshot` — same

**For `src/kingdom/tui/poll.py`**: Do NOT restore anything. The merge_assistant_snapshots function and cursor branching should stay removed.

**For `tests/test_config.py`**: Do NOT restore. Config tests correctly reflect cursor being out of defaults.

**For `tests/test_cli.py`**: Do NOT restore. Doctor tests correctly reflect cursor being out of DEFAULT_AGENTS.

### Why this specific approach?

The `git checkout` for agent.py is safe because that file had a clean cursor-only removal. For test_tui_poll.py, patches are necessary because: (a) two commits touched it, (b) new tests were added *after* the removals that would be lost with `git checkout`, and (c) some restored tests need modification since `merge_assistant_snapshots` is staying dead.

### Risk assessment

The main risk is in the `test_tui_poll.py` restoration. The cursor streaming tests that used `merge_assistant_snapshots` semantics will need updating since poll.py now uses simple concat. If cursor actually emits cumulative snapshots (not deltas), those tests will fail at runtime. You may want to verify cursor's actual behavior before deciding whether the tests need to assert merge semantics (which would mean restoring `merge_assistant_snapshots` too) or concat semantics.

### Decision point for you

Do you want `merge_assistant_snapshots` back or not? Your brief says "simple concat is correct" and "cursor branching in poll.py REMOVED." But many of the cursor tests were specifically testing snapshot-merge behavior. If cursor genuinely emits cumulative snapshots, removing the merge function means cursor streaming output will have duplicated text. If cursor actually emits deltas (like the others), then concat is correct and the old merge-based tests were wrong. That determines which tests to restore vs. rewrite.
