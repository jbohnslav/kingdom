---
from: claude
to: king
timestamp: 2026-02-16T23:54:16Z
---



Let me read the test file and ticket thoroughly.Now let me check the conftest and pytest.ini changes for the gating mechanism, and also look at the current test suite numbers.Now let me run the integration tests to verify they pass.All 22 pass in 4.38s. Let me also verify the default skip behavior works and check the full suite.Clean: 22 skip without the flag, 860+25 in the full fast suite. Now let me read the poller and widgets to understand the full integration surface area that these tests exercise.Good. I now have the complete picture. Here's my review.

---

## Review: Integration Test Suite (Ticket cf1a)

### Overall Assessment

This is a well-crafted integration test suite. The harness is sound, the gating mechanism works correctly (verified: 22 skip without flag, 22 pass with flag in 4.38s), and isolation via `tmp_path` is correct. The choice to mock `Council.create` while keeping the real poller and real file I/O is the right trade-off — it exercises the actual poll→render cycle without requiring real agent backends.

I'll go through your four questions systematically.

---

### (1) Coverage: 22 tests across 11 scenarios

**Well-covered scenarios:**

- **Scenario 1 (boot):** 4 tests — header content, input focus, history renders, empty thread. Thorough.
- **Scenario 2 (keyboard):** 2 tests — Enter sends, Shift+Enter doesn't. Clean.
- **Scenario 3 (send lifecycle):** 2 tests — king message appears, waiting panels mount. The `run_query` mock to `asyncio.sleep(999)` is a nice trick to freeze the UI mid-flight for inspection.
- **Scenario 5 (error):** 1 test — error panel renders. Adequate.
- **Scenario 6 (external updates):** 1 test — external message appears via poll. Good.
- **Scenario 7 (slash commands):** 5 tests — /help, /mute, /unmute, unknown, /quit. Complete.
- **Scenario 10 (isolation):** 1 test — session_id cleared. Covers the 0f27 fix.
- **Scenario 11 (sanitization):** 1 test — no duplicated speaker prefix. Important regression.

**Gaps I see:**

1. **Scenario 4 (stream lifecycle) is thin.** `test_stream_to_finalized` checks that finalized MessagePanels exist after the query completes, but it doesn't verify the **intermediate states**: WaitingPanel → StreamingPanel → MessagePanel. The FakeMember writes a stream event *and* returns a response synchronously, so by the time the test checks, the full lifecycle has already collapsed. There's no test that actually observes a StreamingPanel in the DOM. This is the highest-value gap because streaming display is the TUI's core differentiator.

   To test this properly, you'd need a FakeMember with a delay or a two-phase approach: write the stream file first (which the poller picks up as StreamStarted+StreamDelta), verify the StreamingPanel exists, *then* write the finalized message file. The current `delay` field on FakeMember exists but doesn't help because `asyncio.to_thread` blocks the whole query — you'd need the delay to happen *between* stream file write and finalized message write.

2. **No test for `@member` directed messages.** All send tests use broadcast. The directed path (single member query, no auto-turns, `to != "all"`) is a distinct code path in `send_message()` at line 319-325 that's untested at the integration level.

3. **No test for the thinking panel lifecycle.** The codebase has `ThinkingPanel`, `ThinkingDelta`, `handle_thinking_delta()`, and `thinking_visibility` config — none of which are exercised by integration tests. Since `thinking_visibility` was added in this same branch, there's no integration coverage for auto-collapse or `hide` mode.

4. **Scenario 8 (escape interrupt) doesn't verify ErrorPanel replacement.** `test_escape_interrupts_active_query` verifies that `process.terminate()` was called and `interrupted` is True, but it doesn't check that WaitingPanels were replaced with `*Interrupted*` ErrorPanels in the DOM. That's the user-facing behavior. The reason: the interrupt test manually mounts WaitingPanels but the `action_interrupt()` code replaces them with ErrorPanels — the test just doesn't assert on the replacement.

5. **Scenario 9 (auto-turn) is a single test that doesn't assert on member response content.** `test_follow_up_sequential_round_robin` waits for message files to be written but doesn't verify that the sequential round-robin order is correct in the UI, or that the budget was respected. It's more of a "doesn't crash" test than a behavior test. The existing unit tests in `test_tui.py::TestAutoTurns` cover this well, so the integration gap is lower-priority.

6. **No test for muted member affecting a real query dispatch.** The slash command tests verify the muted set is updated, but there's no integration test where you mute a member, send a message, and verify only unmuted members get queried. Again, unit tests cover this, so medium-priority.

7. **No `/exit` test.** Only `/quit` is tested. Trivial, but it's listed in the ticket scenarios.

---

### (2) FakeMember/harness approach

**Strengths:**
- FakeMember mirrors `CouncilMember`'s interface (name, query, session_id, process, base, branch, preamble). This is solid duck-typing.
- Writing real stream events to real files exercises the real poller — this is the right boundary.
- `patch.object(Council, "create", ...)` is clean — no monkeypatching internals.
- `wait_until()` with bounded timeout is the right pattern for async UI tests.

**Fragility risks:**

1. **Interface drift.** FakeMember isn't enforced by a Protocol or ABC. If `CouncilMember` gains a new required attribute or method signature change, the FakeMembers will fail with confusing attribute errors, not clear test failures. This is the nature of duck-typing. Risk is low because `CouncilMember` is a `@dataclass` with a stable interface, but worth noting.

2. **FakeMember.query writes stream files synchronously before returning.** This means the stream file exists for only a brief window before `run_query()` completes and the finalized message file is written. In the real system, streaming can last minutes. This makes it impossible to test intermediate streaming states (as noted in gap #1 above). To fix this, FakeMember would need an event/barrier mechanism: write stream → signal test → test asserts streaming panel → signal FakeMember → FakeMember returns response.

3. **The `asyncio.sleep(999)` mock for `run_query`** (used in scenarios 3) is a pragmatic hack but fragile if anyone changes the method signature or if Textual's `run_test` has a max timeout. It also means those tests can't verify what happens *after* the query completes.

4. **`str(header.content)` / `str(system_msgs[0].content)` — accessing Textual widget internals.** If Textual changes how `.content` is exposed on `Static`, these break. The alternative (screen snapshot comparison) is worse, so this is an acceptable risk.

---

### (3) Test isolation

**Isolation is strong:**

- Every test gets a fresh `tmp_path` via the `project` fixture. No shared filesystem state.
- `BRANCH = "test/integration"` is a fixed test branch name — shared across tests but each test's `tmp_path` makes this fine.
- `thread_id` fixture creates a fresh thread per test. Good.
- `patch.object(Council, "create", ...)` prevents real agent resolution.
- No global state mutation (no writing to `~/.config`, no environment variable changes).
- `asyncio_mode = auto` gives each test its own event loop.
- Stream file cleanup on mount (`on_mount` cleans stale `.stream-*.jsonl`) means even if a test leaves debris, the next app startup is clean.

**One minor concern:** The `fake_council` fixture creates a `Council(timeout=10, ...)` — the 10-second timeout is fine for tests but the FakeMembers return instantly, so the timeout is never hit. If a test hangs (e.g., `wait_until` times out), the 5.0s timeout in `wait_until` will catch it. The `timeout` in `@pytest.mark.timeout` is absent — consider adding a per-test global timeout (e.g., 10s) to prevent CI hangs if Textual's event loop gets stuck.

---

### (4) Improvements: now vs defer

**Do now** (worth the effort, low risk):

1. **Verify WaitingPanel → ErrorPanel replacement in escape test.** After the first Escape in `test_escape_interrupts_active_query`, assert that:
   ```python
   error_panels = log.query(ErrorPanel)
   assert len(error_panels) >= 1
   ```
   This is 2 lines and catches the most visible user-facing behavior of interrupt. Currently the test only checks `process.terminate()` was called — that's the mechanism, not the UX.

2. **Add a directed `@member` message test.** Send `@claude What do you think?`, verify only claude's WaitingPanel appears (not codex's). This is the other half of the send lifecycle that's completely unexercised.

3. **Add a per-test timeout marker.** Either `@pytest.mark.timeout(10)` (requires pytest-timeout) or a manual guard in `wait_until`. Prevents CI hangs. The 5s `wait_until` timeout helps but doesn't cover all paths (e.g., if `app.run_test()` itself hangs).

**Defer** (high effort, lower value):

4. **Intermediate streaming state test** (StreamingPanel visible during query). Requires restructuring FakeMember with barriers/events. High effort. The unit tests in `test_tui_poll.py` cover the poller's stream lifecycle, and the integration test verifies the full cycle end-to-end. The gap is specifically "StreamingPanel rendered in real Textual DOM during stream" — nice to have, not blocking.

5. **ThinkingPanel integration test.** The thinking feature is new and the unit tests in `test_tui_thinking_persistence.py` exist. Integration coverage would add value but requires FakeMember to emit Claude-style thinking events in the stream file, which means deeper coupling to the NDJSON format. Defer until thinking is more stabilized.

6. **Protocol class for FakeMember.** Creating a `CouncilMemberProtocol` that both `CouncilMember` and `FakeMember` implement would catch interface drift at import time. Low urgency — the interface is stable.

### Summary

| Priority | Item | Effort |
|----------|------|--------|
| Now | Assert ErrorPanel replacement in escape test | 2 lines |
| Now | Add `@member` directed message integration test | ~20 lines |
| Now | Add per-test timeout guard | Trivial |
| Defer | Intermediate streaming state (StreamingPanel visible) | High |
| Defer | ThinkingPanel integration coverage | Medium |
| Defer | FakeMember Protocol enforcement | Low |

The suite is solid for a first pass. 22 tests in 4.4s with clean skip gating is exactly what was scoped. The three "now" items are small additions that close the most visible gaps. Everything else can wait.
