---
from: claude
to: king
timestamp: 2026-02-16T14:12:19Z
---



I'll review the implementation thoroughly. Let me start by reading all the relevant files.Now let me read the tests.Now let me also check `format_thread_history` to understand what gets sent as the prompt, and look at the thread module for context on how messages accumulate.Now let me run the full test suite to confirm everything passes.All 781 tests pass. Now let me look at the design doc to cross-reference intent.Good. I now have a complete picture. Here's my review.

---

## Review: Ticket 3b76 — Auto-turn Round-robin Scheduler

### Overall Assessment

The implementation is clean, well-structured, and matches the design doc's intent closely. The single-coordinator pattern (`run_chat_round`) is the right call — it makes the state machine explicit and avoids the complexity of coordinating N independent workers. The generation counter is a solid preemption mechanism. Tests are thorough and cover the important scenarios.

That said, I found **one bug**, **two race condition concerns**, **one design doc inconsistency**, and **several minor issues**.

---

### Bug: Broadcast mode ignores interrupt/generation checks

**`app.py:375-383`** — In broadcast mode, the initial round uses `asyncio.gather()` with no preemption checks:

```python
if mode == "broadcast" and len(targets) > 1:
    coros = []
    for name in targets:
        member = self.council.get_member(name)
        if member:
            stream_path = tdir / f".stream-{name}.jsonl"
            coros.append(self.run_query(member, "", stream_path))
    await asyncio.gather(*coros)
```

This is fine for the initial parallel burst — you want all members to fire simultaneously. But compare with the sequential path at line 386-393 which checks `self.interrupted` and `self.generation != generation` **before each member**. If the user hits Escape during the initial broadcast, the gather will still wait for all coroutines to complete (they'll each run to completion in their respective threads). The processes get terminated via `action_interrupt()`, but the `gather` still blocks until all `asyncio.to_thread()` calls return.

This isn't catastrophic (the terminated processes will exit quickly), but it means there's a brief delay before auto-turns check the interrupt flag. Acceptable, but worth noting.

### Race Condition Concern #1: Generation check timing in auto-turns

**`app.py:398-410`** — The generation check happens *before* mounting the WaitingPanel and starting the query:

```python
for name in active:
    if self.interrupted or self.generation != generation:
        return
    member = self.council.get_member(name)
    ...
    log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
    ...
    await self.run_query(member, "", stream_path)
```

The design doc says: "User sending a new message during auto-mode: current generation completes, auto-mode pauses, user message processed, auto-mode resumes."

But the implementation doesn't *pause and resume* — it **terminates**. When `self.generation != generation`, the coordinator returns entirely. The new message from `send_message()` launches a fresh `run_chat_round()` with the new generation. This means auto-turns from the first generation are lost — they don't resume after the user's message is processed.

This is actually **the right behavior** in practice (the new `run_chat_round` starts fresh auto-turns after the new broadcast), but the ticket acceptance criteria says "auto-mode pauses... auto-mode resumes" which implies continuity. Recommend updating the ticket/design doc language to match reality: "current generation stops, new message triggers fresh rounds."

### Race Condition Concern #2: WaitingPanel ID collision

**`app.py:406`** — Auto-turn WaitingPanels use `id=f"wait-{name}"`:

```python
log.mount(WaitingPanel(sender=name, id=f"wait-{name}"))
```

If a member's previous WaitingPanel wasn't yet replaced by the poller (e.g., the finalized message poll hasn't run yet), mounting a new WaitingPanel with the same ID will cause a Textual `DuplicateIds` error. In practice, `run_query()` persists the message to thread files, and the poller replaces the panel via `handle_new_message()` — but there's a timing window between the message file being written and the next 100ms poll cycle running.

The `handle_new_message` code at lines 531-563 does query for `wait-{name}` and remove it. But the auto-turn loop in `run_chat_round` synchronously mounts a new `wait-{name}` right after `await self.run_query()` returns — and `run_query` returns *before* the poller has a chance to process the finalized message. The poller runs on `set_interval(0.1)` which is a separate async task. So the sequence is:

1. Auto-turn round 1: mount `wait-claude`, run query, query returns
2. Auto-turn round 2 (next iteration): mount `wait-claude` again → **duplicate ID**

The poller hasn't had a chance to run between steps 1 and 2 because the coordinator is a single coroutine that only yields at `await self.run_query()` (which is `asyncio.to_thread` — it does yield, but `run_query` itself doesn't wait for the poller to process the finalized message).

**Wait** — actually, let me re-examine. The `run_query` calls `add_message()` to persist the response. Then the `finally` block cleans up the stream file. Then control returns to `run_chat_round`, which does the `if self.interrupted...` check, then mounts a new `wait-{name}`. The poller runs on the same event loop, so it *could* run between the `await` return and the next line... but there's no `await` between `run_query` returning and the new `WaitingPanel` mount. So the poller tick won't interleave there.

The question is: does `handle_new_message` (from the poller) remove the old `wait-{name}` panel before the coordinator mounts a new one? It can't — the poller hasn't had CPU time yet.

**However**, looking more carefully: `run_query` returns after `asyncio.to_thread()` completes. When the event loop resumes the coordinator coroutine, pending timer callbacks (like `poll_updates`) execute between turns of the event loop. But in practice, the coordinator's next statement (`if self.interrupted...`, then `log.mount(WaitingPanel(...))`) runs in the *same* event loop turn as the resumed coroutine. So the poller won't fire between `run_query` returning and the new `WaitingPanel` mount.

**This is a real bug.** On the second auto-turn round for the same member, a `wait-{name}` panel may still exist because the poller hasn't replaced it with a `MessagePanel` yet.

**Recommended fix:** Add an `await asyncio.sleep(0)` (or even `await asyncio.sleep(0.15)`) between consecutive members' auto-turns, or remove/query the old panel explicitly before mounting the new one. Alternatively, use unique panel IDs like `wait-{name}-{round}`.

### Design Doc Inconsistency: `auto_rounds` validation

The design doc at line 161 says:

> `auto_rounds` | int | `3` | Must be positive (> 0)

But the implementation allows `auto_rounds >= 0` (line 197-198 of config.py):

```python
if auto_rounds < 0:
    raise ValueError(f"council.auto_rounds must be non-negative, got {auto_rounds}")
```

The test at line 237 confirms `auto_rounds=0` is valid. The code is correct (0 = disable auto-turns is a good feature), but the design doc should be updated to say "non-negative (>= 0)".

### Minor Issues

1. **`run_query` ignores its `prompt` parameter.** At `app.py:329-330`, `run_query` accepts a `prompt` argument but never uses it — it always calls `format_thread_history()` to build the prompt from scratch:

   ```python
   async def run_query(self, member, prompt: str, stream_path: Path) -> None:
       ...
       prompt_with_history = format_thread_history(tdir, member.name)
       response = await asyncio.to_thread(member.query, prompt_with_history, ...)
   ```

   The `prompt` parameter is dead code. The callers at lines 320, 382, 393, 410 pass either `text`, `""`, or `""`. None of it matters. The parameter should either be removed or used. Since the directed message path (line 320) passes `text` but it's ignored, the directed message also gets full thread history — which is correct behavior, but misleading in the calling code.

2. **Muted member still queried in broadcast initial round.** Look at `app.py:1139-1146` in the test and the code flow:

   `send_message()` calls `parse_targets()` which excludes muted members from `targets`. Those filtered targets are passed to `run_chat_round()`. But the test at line 1140 passes `["claude", "codex", "cursor"]` directly — codex included despite being muted. This works because the test bypasses `send_message()` and calls `run_chat_round()` directly.

   In the real flow, `parse_targets()` would have already excluded codex, so `targets` would be `["claude", "cursor"]`. Then `run_chat_round` queries those two in the initial round, and also filters by `self.muted` for auto-turns. This means the test is correct but the comment "all 3 queried (targets already decided by send_message)" is misleading — in real use, codex would never reach `run_chat_round` at all. The test is testing that auto-turns independently filter by mute, which is fine, but the initial round assertion (`codex.call_count == 1`) only passes because the test bypasses the real entry point.

3. **No visual indicator for auto-turns.** The design doc mentions StatusBar showing "auto-round status" but the implementation doesn't update the status bar during auto-turns. Users can't tell if the system is in round 1/3 or 3/3. Not blocking, but a UX gap.

4. **`run_chat_round` doesn't handle the case where all members are muted.** If `self.muted` contains all member names, the auto-turn loop at line 397 produces `active = []` and silently skips. This is actually fine (no crash, no wasted queries), but the user gets no feedback that auto-turns were skipped because everyone is muted.

### Test Coverage Assessment

The tests are strong. Key scenarios covered:
- Auto-turns fire correctly (count verification)
- `auto_rounds=0` disables auto-turns
- Interrupt stops mid-round
- Generation mismatch stops auto-turns
- Muted members skipped in auto-turns
- Directed messages skip auto-turns entirely
- Sequential mode preserves order
- Errors don't stop the round
- Council.create passes new fields from config
- Config validation for `auto_rounds` and `mode`

**Missing test:** No test for the duplicate WaitingPanel ID issue described above. A multi-round auto-turn test with panel mounting assertions would catch this.

**Missing test:** No test for `auto_rounds=1` — the boundary case between "just initial" and "initial + auto."

### Summary

| Priority | Issue |
|----------|-------|
| **Fix** | WaitingPanel ID collision across auto-turn rounds (duplicate Textual widget IDs) |
| **Fix** | Remove or use the dead `prompt` parameter in `run_query()` |
| **Doc** | Update design doc: `auto_rounds` validation should say `>= 0` not `> 0` |
| **Doc** | Update ticket AC: "auto-mode pauses/resumes" should say "current generation stops, new message triggers fresh rounds" |
| **Minor** | Status bar doesn't show auto-turn progress |
| **Minor** | No user feedback when all members muted during auto-turns |
