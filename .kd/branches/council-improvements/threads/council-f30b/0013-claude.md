---
from: claude
to: king
timestamp: 2026-02-15T02:42:40Z
---

Good, 1c4b is in backlog where it belongs. Now I have the full picture.

---

## Tickets vs. Design: Alignment Review

### What's in good shape

The design has been substantially improved since the earlier draft. The new Phase 0 (e756) is smart — it resolves the streaming foundation before everything else depends on it. The dependency graph is mostly correct:

```
e756 (stream-json foundation)
├── 6412 (async error handling) — needs stream-json to show live progress
├── 3e60 (kd chat TUI) — needs .jsonl stream files
│
a9c9 (richer status) — no deps, standalone
├── a4f5 (council list enrichment) — needs richer status to display
│
70f6 (show pagination) — no deps, standalone
├── d09d (visual turn separation) — needs pagination to know what "turn" means
│
1e3d (auto-commit) — no deps, standalone
```

Three tickets correctly closed: 41fb (already done), 520a (research complete), 549b (already works via config).

### Problem 1: Missing ticket for config schema extension

The design's Phase 0 says: "Config schema extension: Add `council.chat` and `council.auto_commit` to `config.json` schema. Update `VALID_COUNCIL_KEYS` in `config.py`, add `ChatConfig` dataclass + validation."

There's no ticket for this. It's bundled into the Phase 0 description but e756 is specifically about stream-json/NDJSON parsing. Config schema work is a different concern — it touches `config.py` (dataclasses, validation, `VALID_COUNCIL_KEYS`), not `agent.py`/`base.py`.

**Recommendation:** Either fold it into 1e3d (which needs `council.auto_commit`) or create a small dedicated ticket. I'd lean toward: 1e3d adds `auto_commit` to the config schema as part of its own work, and the `council.chat` config gets added when 3e60 (chat TUI) or a Phase 3 ticket needs it. Don't pre-build config for features that don't exist yet.

### Problem 2: Phase 3 has no tickets

The design describes Phase 3 (group chat mode) with specific requirements — auto-rounds, thread history injection, interrupt semantics, round-robin — but there are zero tickets for any of it. The 3e60 ticket covers Phase 2 only (basic TUI, no auto-mode).

**Recommendation:** Don't create Phase 3 tickets yet. Phase 3 depends entirely on Phase 2 being built and dogfooded. You'll learn what group chat actually needs by using `kd chat` for a while. Creating tickets now would be speculative. The design doc captures the intent; tickets can be created when you're ready to build Phase 3. Just make a note in the design that Phase 3 tickets are deferred.

### Problem 3: 6412 is too big

Ticket 6412 has five acceptance criteria that are really three separate pieces of work:

1. **Better error messages** (fix `Error: None`) — this is a parsing/display fix in `base.py:139` and `council.py:120`
2. **Automatic retry** — new retry logic in `query_to_thread()` or the worker
3. **Per-member reset + `kd council retry`** — two new CLI commands

These have different complexities. The error message fix is probably 30 minutes. Retry logic is a design decision (when, how many times, session reset between retries). New CLI commands are mechanical but need tests.

**Recommendation:** Either accept that 6412 is a "big ticket" that takes a full work session, or split it into two: (a) "meaningful errors + automatic retry" and (b) "`council reset --member` + `council retry`". I'd keep it as one — the pieces are coupled enough that splitting creates coordination overhead.

### Problem 4: `watch_thread()` streaming isn't in any ticket

The design (Phase 1) says: "Update `watch_thread()` to tail `.stream-{member}.jsonl` files alongside polling for finalized messages." This is the single most impactful UX improvement for the existing CLI workflow — it's what turns the 4-minute spinner into live streaming output. But no ticket owns this work.

6412 says "Progress/status visibility while council queries are running" which is vague. The watch streaming work is more specific: tail `.stream-*.jsonl` files, extract text_delta, show accumulated text per member, replace with final response when message file lands.

**Recommendation:** Either add a specific acceptance criterion to 6412 ("watch_thread() tails .stream-{member}.jsonl files and displays incremental text during execution"), or create a new ticket. I'd add it to 6412 since it's the same "no visibility while running" problem.

### Problem 5: a4f5 dependency on a9c9 may be unnecessary

a4f5 (council list enrichment) depends on a9c9 (richer status). But looking at the acceptance criteria, a4f5 says "status is derived from thread message files (presence = responded, absence = pending, error field = errored)." That's the thread-based status that already exists in `thread_response_status()` — it doesn't need the PID-based "running/interrupted/timed out" states from a9c9.

**Recommendation:** Either drop the dependency (a4f5 can show responded/pending/errored from thread files alone), or update a4f5's criteria to say it should show the richer states from a9c9. Dropping the dep is simpler and lets the two be worked in parallel.

### Problem 6: 1e3d has no dependency on e756 but probably should share the worker flow

1e3d (auto-commit) runs in the worker process after all responses land. e756 (stream-json) changes the parsing and stream file format in the same worker process. If e756 lands first (which it should, being P1), 1e3d's implementation is straightforward. If someone tries to build 1e3d before e756, they'd be building against the old stream file format (`.md` → `.jsonl` rename happens in e756).

**Recommendation:** Add `deps: [e756]` to 1e3d. It's not a hard dependency (auto-commit doesn't care about stream file format), but it avoids merge conflicts in `worker.py`.

### Problem 7: 3e60 (chat TUI) is missing key acceptance criteria

Comparing the design's Phase 2 requirements to 3e60's criteria:

| Design requirement | In ticket? |
|---|---|
| Textual app, separate pane | Implied by "interactive terminal UI" |
| Open existing thread or create new | Missing |
| Slash commands: /mute, /unmute, /help, /quit | Missing |
| Stream from .jsonl files | Implied by "display inline as they arrive" |
| Textual as optional dependency | Missing |
| asyncio bridge | Missing (implementation detail, fine to omit) |
| Handle .stream file deletion gracefully | Missing (implementation detail, fine to omit) |
| Color-coded panels per member | Missing |

**Recommendation:** Add to 3e60's acceptance criteria:
- `kd chat --new` creates a fresh thread; bare `kd chat` resumes current thread
- `/mute`, `/unmute`, `/help`, `/quit` commands work
- Textual is an optional dependency; `kd chat` shows install hint if missing
- Responses are color-coded per member

### What's unnecessary or over-scoped

**d09d (visual turn separation) could be folded into 70f6 (pagination).** They're both about `council show` display. 70f6 introduces the concept of "turns" as the unit of pagination; d09d adds visual separators between turns. If you're already rewriting the display loop to paginate by turns, adding a separator is one extra `console.print(Rule())` call.

**Recommendation:** Merge d09d into 70f6. One ticket: "council show: paginate by turns with visual separation." This reduces ticket count and eliminates a dependency edge.

### Suggested execution order

Given the dependencies and coupling:

```
1. e756 — stream-json foundation (unblocks everything)
2. a9c9 — richer status (standalone, unblocks a4f5)
3. 6412 — async error handling + watch streaming (depends on e756)
4. 70f6+d09d — show pagination + visual turns (standalone, merge into one)
5. a4f5 — council list enrichment (drop a9c9 dep or do after a9c9)
6. 1e3d — auto-commit (standalone but cleaner after e756)
7. 3e60 — kd chat TUI (the big one, depends on e756)
```

Items 2, 4, 5, 6 are all independent of each other once e756 is done, so they can be parallelized or ordered by mood. 3e60 is last because it's the largest and benefits from all the CLI fixes being done first (you'll dogfood the improved CLI while building the TUI).

### Summary of recommended changes

1. **Merge d09d into 70f6** — they're the same `council show` rewrite
2. **Add watch streaming criterion to 6412** — most impactful UX fix, needs a home
3. **Add deps: [e756] to 1e3d** — avoids merge conflicts
4. **Consider dropping a4f5→a9c9 dependency** — a4f5 can use thread-based status alone
5. **Flesh out 3e60's acceptance criteria** — thread resumption, slash commands, optional dep, colors
6. **Don't create Phase 3 tickets yet** — dogfood Phase 2 first
7. **Don't pre-build `council.chat` config** — add it when Phase 3 work begins
8. **Add `kd council watch` streaming to 6412 AC** — this is the "visibility" criterion made concrete
