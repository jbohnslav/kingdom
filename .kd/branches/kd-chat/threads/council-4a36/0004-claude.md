---
from: claude
to: king
timestamp: 2026-02-15T23:58:55Z
---



I'll do a comprehensive review. Let me start by gathering the current state of everything.Good — only P2/P3 tickets remain open. Let me now show the closed tickets to understand what was done, then read all the source code.Now let me read all the TUI source files and modified base files.Now let me read the CLI chat command and check the tests.Now let me check the existing tests for config validation and read any remaining test files for regressions.Good — 719 tests pass, 3 skipped, no failures. The TUI actually launched with `kd chat` and displayed the thread history. Let me kill that background process and do a few more targeted checks.Now let me check a few specific things I noticed in the code.That confirms a significant finding. Let me verify a few more things.Now let me check for a king message panel being created in `send_message()` and look at how auto-scroll is tracked.Let me also check the pyproject.toml for the textual dependency group, and look at the council `__init__.py` to verify the import path.Let me check how the pyproject.toml specifies the dependency group.Now let me check one more thing — the `finalized_members` state doesn't reset between king messages, which could be a problem across rounds.Let me verify one more code path — what happens when the king's message body gets sent as the prompt (does the raw `@mention` text get sent to agents, or is it stripped?).Now let me also check the `send_message` flow for king message rendering — the king's own message is written to the thread file but never shown in the TUI as a MessagePanel during `send_message()`. It would only appear on the next poll cycle via `poll_messages()`. Let me verify that's the case.I see — the king's message does appear via `poll_updates()` on the next 100ms cycle. That's technically fine but slightly janky — there's a brief moment where WaitingPanels appear with no king message above them. Let me check how `council_ask` in cli.py handles this same sequence for comparison.Here's the full review.

---

## Review: kd-chat Phase 1 Implementation

### Test Suite Status

**719 passed, 3 skipped, 0 failures.** No regressions. The `kd chat` command launched successfully and rendered thread history from the current thread. All three new test files (`test_tui.py`, `test_tui_poll.py`, `test_tui_widgets.py`) pass.

### Design Fidelity

The implementation matches the design doc well in its scope and architecture. The key decisions are correctly reflected:

- Thread files as source of truth
- Textual as optional dependency group with lazy import guard
- `kingdom/tui/` module structure (`app.py`, `widgets.py`, `poll.py`)
- File polling at 100ms via `set_interval`
- Widget lifecycle (WaitingPanel → StreamingPanel → MessagePanel)
- Config schema additions (`auto_rounds`, `mode`, `preamble`)
- `self.process` handle on `CouncilMember` with PID tracking
- Direct `Council.create()` usage (not shelling out to CLI)

### Ticket Status

All 9 P1 tickets are correctly closed. The P2/P3 tickets remain open. The ticket 0245 (smoke test) was added per the earlier review recommendation — good.

---

### Bugs

#### BUG 1: TUI never writes member responses to thread files (Critical)

`app.py:run_query()` calls `member.query()` which returns an `AgentResponse`, but the response is **never written to a thread message file**. Compare with `council_ask()` in `cli.py` which calls `add_message(..., body=response.thread_body())` after each response, and `query_to_thread()` which does the same.

This means:
- After the TUI dispatches a query and the agent responds, the response **only exists in the `.stream-{member}.jsonl` file** (which `query_once()` doesn't clean up when called directly — only `query_to_thread()` does that).
- `kd council show` won't show the response.
- If you close and reopen the TUI, the response is gone.
- The thread file source-of-truth contract from the design doc is broken.

**This is on ticket 16e1.** It should be reopened.

#### BUG 2: `finalized_members` never resets across rounds

`ThreadPoller.finalized_members` accumulates forever. Once claude finalizes in round 1, the poller will ignore claude's stream file in round 2. There's no mechanism to reset it when a new king message arrives. For Phase 1 (single round per user message), this is mostly fine — the poller is effectively single-use per query cycle. But it will break badly for Phase 2 auto-turns, and it's fragile even now if the user sends a second message.

**This is on ticket fe84** (the poller). It should be noted in the worklog and fixed before Phase 2 work starts. Could also be handled as a prerequisite in 3b76 (auto-turn scheduler).

#### BUG 3: King message not rendered immediately in `send_message()`

When the user sends a message, `send_message()` writes the king message to the thread file and creates WaitingPanels, but never creates a `MessagePanel` for the king's own message. The king message only appears on the next 100ms poll cycle when `poll_messages()` picks it up. This creates a brief visual glitch where WaitingPanels appear first, then the king message pops in above them on the next poll.

This should be fixed by mounting a `MessagePanel` for the king directly in `send_message()`, before the WaitingPanels. Minor UX bug — doesn't need a ticket reopen, but should be fixed.

#### BUG 4: `asyncio.get_event_loop()` is deprecated

`app.py:210` uses `asyncio.get_event_loop().create_task(...)`. This is deprecated since Python 3.10 and will emit a `DeprecationWarning` when there's no running event loop. Inside a Textual app, this happens to work because Textual manages the event loop, but the correct Textual pattern is `self.run_worker()` or `asyncio.create_task()` (available when called from an async context). Since `send_message()` is called from `on_key()` which is sync, the right Textual approach is `self.call_later()` wrapping an async method, or converting `send_message` to use Textual's worker API.

Not currently broken, but will emit warnings and is fragile.

### Missing from Design

#### Missing: Session save on exit

The design says the TUI manages `Council` instances directly. `council_ask()` in `cli.py` calls `council.save_sessions()` after queries complete. The TUI never calls `save_sessions()`. This means session IDs (for `--resume`) are lost when the TUI exits. For Phase 1 this is low-impact since council queries are mostly stateless, and Phase 2 explicitly drops `--resume` in favor of thread history injection. But it's a deviation from the current CLI behavior.

#### Missing: Stream file cleanup after query completion

`query_to_thread()` deletes stream files after writing the finalized message. The TUI's `run_query()` doesn't clean up stream files at all. They'll linger as orphaned `.stream-{member}.jsonl` files. This could confuse the poller on subsequent queries (the retry detection handles file recreation, but stale files from a completed query are a different case).

#### Missing: Auto-scroll behavior is declared but not implemented

The design specifies "scroll to bottom when new content arrives, but only if the user is already at the bottom." The code sets `self.auto_scroll = True` and uses it, but **never sets it to False**. There's no scroll position tracking. If the user scrolls up, new content will still yank them back down. The `auto_scroll` field is a stub.

### Code Quality

#### Strengths

- **Clean module separation.** `poll.py` is pure data (no Textual imports), `widgets.py` is pure display, `app.py` orchestrates. Testable.
- **Poll events as typed dataclasses.** The `PollEvent` union type is clean and makes event handling explicit.
- **Good test coverage for polling logic.** The `TestThreadPoller*` classes cover the important state transitions: new messages, streaming start/delta, finalization, retry detection, external streams.
- **Config validation is thorough.** The three new keys (`auto_rounds`, `mode`, `preamble`) have proper type checking, range validation, and the existing unknown-key guard still works.
- **`CouncilMember.process` lifecycle is correct.** Set immediately after `Popen`, cleared in `finally` block. PID written to `AgentState` for external monitoring. Thread-safe since the `finally` runs on the same thread as `query_once()`.

#### Issues

1. **`send_message()` doesn't handle the case where `parse_targets()` returns an empty list.** If all `@mentions` are invalid members, `parse_targets()` falls back to broadcasting to all members — that's correct. But if `self.member_names` is empty (thread has no members besides king), `targets` would be `[]`, and the `to = targets[0] if len(targets) == 1 else "all"` line would set `to = "all"` but create no WaitingPanels and dispatch no queries. The king message would be written with `to: all` but nothing happens. Edge case, but worth noting.

2. **`read_message_body()` in `poll.py` duplicates frontmatter parsing.** `thread.py` already has `parse_message()` which does the same thing (and handles more edge cases like refs, timestamps). `read_message_body()` is a simpler/faster version, which is defensible for polling performance, but it introduces two parsing paths that could diverge. The bigger concern: `poll.py` parses the sender from the filename (`stem.split("-", 1)`), not from the `from:` field in the frontmatter. These should always match, but it's a latent inconsistency.

3. **`WaitingPanel` has `height: 1` in CSS.** This means it's a single character tall — the border title "codex — waiting..." renders, but the panel body is essentially invisible. This is likely intentional (collapsed placeholder), but `height: 1` with border means the border itself consumes the height and the panel may render oddly depending on terminal/Textual version. Worth checking visually. I saw it render correctly in the `kd chat` output I captured, so this may be fine.

4. **`color_for_member()` uses `hash()` which is randomized per Python process.** Python randomizes `hash()` by default (via `PYTHONHASHSEED`). This means the same member name gets different colors in different TUI sessions. The design says "consistent across session" which is true (within one session), but the colors change every time you restart the TUI. Use a deterministic hash (e.g., `hashlib.md5(name.encode()).digest()`) if you want cross-session consistency.

5. **`run_query()` error handling is asymmetric.** When `member.query()` returns with `response.error and not response.text`, it creates an ErrorPanel and removes the waiting panel. But when `response.error and response.text` (partial timeout — the agent produced some output before timing out), the error is silently swallowed. The response text *would* eventually appear as a finalized message via the polling path (if someone writes it to a thread file — which they don't, per Bug 1). This is a second consequence of Bug 1: partial timeout responses are completely lost.

### Recommendations

#### Tickets to reopen

- **16e1** — `run_query()` must write finalized responses to thread files (Bug 1). This breaks the core "thread files as source of truth" invariant.

#### Bugs to fix alongside 16e1

- King message not rendered immediately (Bug 3) — fix in `send_message()`
- Stream file cleanup after query completion — add unlink to `run_query()`
- `asyncio.get_event_loop()` deprecation (Bug 4) — switch to Textual worker pattern

#### Backlog tickets to file

1. **`finalized_members` never resets across rounds** — will break Phase 2. File now so it's tracked.
2. **`auto_scroll` is a stub** — declared but never driven by scroll position. The design explicitly specifies "don't yank if user scrolled up."
3. **`color_for_member()` is non-deterministic across sessions** — use deterministic hash for cross-session consistency.
4. **`read_message_body()` duplicates `parse_message()` parsing** — latent inconsistency between sender-from-filename and sender-from-frontmatter.
