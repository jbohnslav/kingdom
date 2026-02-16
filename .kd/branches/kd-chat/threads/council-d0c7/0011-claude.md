---
from: claude
to: king
timestamp: 2026-02-16T18:27:30Z
---



Good question from the King. Let me re-read the current implementation carefully against his stated ideal, then address each of your questions.Now let me look at the config to understand what `auto_rounds` currently defaults to.Now let me read the design doc section on auto-turns one more time to compare the King's new vision against what's written.OK. I have a clear picture of the current state, the King's stated desire, and your proposed interpretation. Here's my analysis.

---

## Analysis: Redesigning Auto-turns

### Does your interpretation match the King's intent?

**Almost, but point #2 needs adjustment.** Let me re-read the King's words carefully:

> "everyone responds once to the king (in parallel, like karpathy's llm council) and then waits for the king to respond. after that, it becomes a round-robin chat. N max messages total before the king responds."

I read "after that" as referring to **after the king responds to the initial broadcast** — i.e., the king's *second* message. So the flow is:

1. **King message → broadcast (parallel) → stop.** Wait for king.
2. **King responds again → round-robin (sequential), up to N messages total → stop.** Wait for king.
3. Repeat step 2.

Your interpretation at point #2 says "No broadcast on follow-ups — the conversation is already established." I agree with this. But I want to flag a subtlety: the King said "it becomes a round-robin chat" — he's describing the *auto-turns* portion, not asking the king's follow-up to only trigger one member. I believe the King means:

- Follow-up king messages still go to everyone (they see it via thread history), but the **responses** come back one at a time (round-robin), not in parallel.
- The N-message budget governs how many sequential responses happen before the system stops and waits for the king again.

So the difference between message 1 and message 2+ isn't "broadcast vs. single target" — it's "broadcast (parallel) vs. round-robin (sequential)." Both query all unmuted members. The initial message queries them simultaneously; follow-ups queue them one-by-one.

**However**, there's a strong argument that follow-ups should *also* broadcast in parallel. The King's complaint was about getting 6 messages when he just said "hi" — that's a volume problem, not a parallelism problem. The fix is: broadcast, then stop. No auto-turns on the first message. After the conversation is established (follow-up messages), round-robin is fine because members are building on each other's responses and order matters.

I think the simplest correct interpretation is:

| Message | Dispatch | Auto-turns |
|---------|----------|------------|
| First king message in thread | Broadcast (parallel) | None. Wait for king. |
| Subsequent king messages | Broadcast (parallel) | Up to N total sequential messages, then wait for king. |
| `@member` | Single member | None. |
| `@all` (on any message) | Broadcast (parallel) | Up to N auto-turns, like follow-ups. |

The key insight: **auto-turns only activate after the conversation has context worth discussing.** The first broadcast is just gathering initial positions. Once the king has read those and responded, there's substance for members to react to each other — that's when round-robin adds value.

### Should N default to `len(members)` or higher?

**Default to `len(members)`** — so each member speaks once per king turn. This is the "one complete round" intuition.

With 3 members, N=3 means after the king speaks, each councillor responds once sequentially, then it stops. If the king wants more discussion, they send another message (even just "continue" or "go on"). This keeps the human in control.

The config key `auto_rounds` (currently meaning "number of complete rounds") should be **renamed or reinterpreted** to mean "max messages" (a budget). Rename `auto_rounds` → `auto_messages` for clarity, default `len(members)`. Or keep `auto_rounds` but interpret it as "rounds where each unmuted member speaks once" — so `auto_rounds=1` with 3 members = 3 messages. The current `auto_rounds=3` with 3 members = 9 messages, which is way too many.

**Recommendation:** Rename to `auto_messages`, default to 0 (no auto-turns — the King's stated preference for the initial broadcast). Then the coordinator counts total messages dispatched and stops at the budget. Simple, no "rounds" abstraction needed.

Actually, wait. Re-reading the King: "N max messages total before the king responds." The budget is messages, not rounds. But the *default* should be `len(members)` so each gets one turn. Rename to `auto_messages`, default `len(members)`. For the first message in a thread, override to 0.

### First-message vs. follow-up distinction

**Infer from thread history.** Don't track a flag. The rule is simple:

> If the thread has no prior member responses when the king sends a message, it's the first message. Otherwise it's a follow-up.

In code: check if `list_messages()` contains any messages with `from_ != "king"` before the current king message. If not, this is the opening message — broadcast only, no auto-turns.

This is one `list_messages()` call at the top of `run_chat_round()`. No new state, no per-thread flags, crash-safe (if TUI restarts, it re-infers correctly from files).

### @mention override for round-robin ordering

The King said: "llms and the king can @ each other to override the round robin, and make their turn next."

For the king, this is straightforward — `@member` already works and dispatches to a single member. But "LLMs @ each other" is a different beast. It means parsing member responses for `@mentions` and reordering the round-robin queue.

**Recommendation:** Defer LLM-to-LLM @mentions. It requires:
- Parsing member response text for `@member` patterns
- Reordering the scheduling queue mid-round
- Deciding what to do about chains (@claude mentions @codex who mentions @cursor)
- Risk of infinite loops if members keep @mentioning each other

The king's @mentions work today. LLM @mentions are a future feature — file a backlog ticket. The round-robin ordering from config is predictable and sufficient for now.

### Simplest implementation path

The changes to `run_chat_round()` are minimal:

1. **Add a "is this the first message?" check** at the top of `run_chat_round`:
   ```
   messages = list_messages(base, branch, thread_id)
   has_prior_responses = any(m.from_ != "king" for m in messages)
   ```
   If `not has_prior_responses`, set effective `auto_messages = 0`.

2. **Replace the double loop** (`for _round in range(auto_rounds): for name in ...`) with a single message-budget loop:
   ```
   messages_sent = 0
   while messages_sent < auto_messages:
       name = next_member(...)  # cycle through member_names
       ... query ...
       messages_sent += 1
   ```

3. **Rename `auto_rounds` → `auto_messages`** in config, Council dataclass, and validation. Default to 0, and have `run_chat_round` use `len(self.member_names)` when the config value is 0 (or make the default `len(members)` computed at Council.create time — but 0-means-default is simpler for config).

Actually, rethinking the default: `auto_rounds=0` currently means "disabled." If we rename to `auto_messages`, we need a clean way to express "disabled" vs "use default." Options:
- `auto_messages = -1` → disabled, `0` → use `len(members)`, `N` → use N. Ugly.
- `auto_messages = 0` → disabled (no auto-turns ever), `null`/absent → use `len(members)`, `N` → use N. This matches the existing pattern where absence = default.

**Simplest:** Keep the config key as `auto_messages`, default to `len(members)` (computed at runtime in Council.create or in `run_chat_round`). Value of 0 means disabled. The first-message check overrides to 0 regardless of config.

4. **`send_message` stays mostly the same.** Broadcast still calls `run_chat_round`. The coordinator decides whether auto-turns happen based on thread history. The `@member` directed path already skips auto-turns.

### Summary of recommendations

| Decision | Recommendation |
|----------|---------------|
| Interpretation | Broadcast (parallel) on every king message. Auto-turns (sequential) only after first exchange is established. |
| Budget unit | Messages, not rounds. Rename `auto_rounds` → `auto_messages`. |
| Default N | `len(unmuted_members)` — one turn each. |
| First-message detection | Infer from thread history: no prior member responses → no auto-turns. |
| `@all` override | Treat like a broadcast follow-up (parallel + auto-turns). |
| LLM @mentions | Defer. File backlog ticket. Too complex for this change. |
| Config compat | `auto_rounds` in existing configs should either be migrated or accepted as an alias. Since this is pre-release, just rename — no backwards compat needed. |

The total diff is small: rename a config field, simplify the double loop in `run_chat_round` to a single budget counter, add one `list_messages` call to detect first-message. Tests update accordingly.
