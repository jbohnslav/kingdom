---
from: claude
to: king
timestamp: 2026-02-16T21:26:38Z
---



Let me read the ticket first.Now let me look at the current test files and the app structure to understand what we're working with.Alright, I've read the ticket and explored the codebase thoroughly. Here's my take on making a real plan for these integration tests:

**The ticket is overly ambitious and needs scoping down.** Here's what I see:

**Current reality:**
- All existing TUI tests (~3,000 lines across 4 files) use direct instantiation + mocking. Zero use of `app.run_test()` or Pilot anywhere.
- ChatApp has deep coupling to file system (ThreadPoller scanning real files every 100ms), Council (real API calls), and background workers (`run_worker()`).
- The ticket lists 3 phases, a full test matrix, diagnosis notes about session isolation bugs — it's trying to do too much.

**What I'd actually plan:**

**Phase 1 should be minimal and focused:** Get one real Textual integration test working end-to-end. That means:

1. **A fixture that builds a fake environment** — tmp_path with branch layout, thread dir, pre-canned messages. This part is straightforward since the existing unit tests already do `ensure_branch_layout()` + `create_thread()` + `add_message()`.

2. **Mock the Council, not the poller.** The poller reads real files — that's fine and fast. The Council makes API calls — that's what needs faking. A mock Council that writes canned response files to the thread dir would let us test the full poll→render cycle with real file I/O.

3. **Start with 3-4 scenarios, not the full matrix:**
   - App boots, existing history renders correctly
   - Type a message, press Enter, see king message + waiting panels appear
   - Stream file appears → waiting→streaming→finalized transition
   - Error response renders ErrorPanel

4. **The pytest marker/gating (Phase 2)** is trivial — a `@pytest.mark.textual_integration` marker and a `conftest.py` that auto-skips unless `--run-textual-integration` is passed. Do this first, not second, so we have the gate from day one.

**What I'd defer or cut:**
- Layout testing at multiple terminal sizes — low value, high maintenance. Textual's own test framework handles this poorly in my experience.
- Visual/snapshot testing — the ticket wisely marks this optional, and I'd keep it firmly out of scope.
- The "diagnosis notes" about session isolation and label duplication — those are bugs to fix in separate tickets, not integration test concerns. Testing for the absence of bugs you haven't fixed yet is backwards.
- Phase 3 (slash commands, interrupt) — correctly blocked on deps, leave it.

**The hard part** is going to be timing. The poll loop runs every 100ms via `set_interval()`. In Pilot tests, we need to either:
- Let real time pass (slow, flaky)
- Manually pump the poll by calling `app.poll_updates()` directly after writing files
- Use `pilot.pause()` with bounded waits

I'd lean toward writing files then calling `await app.poll_updates()` directly in tests, bypassing the timer. It's not "pure" integration but it eliminates timing flakiness, which is the #1 killer of Textual integration test suites.

**Question for the group:** Does anyone have a strong opinion on whether we should test through the real timer or pump manually? The tradeoff is realism vs. reliability.
