---
id: "cf1a"
status: closed
deps: []
links: [council-c86e]
created: 2026-02-16T11:21:29Z
type: task
priority: 2
---
# Textual integration tests for kd chat

Build end-to-end integration coverage for `kd chat` using Textual's `app.run_test()` + `Pilot` so we verify real UI behavior, not only unit-level methods.

## Current State (2026-02-16)

- Existing TUI tests (~3,000 lines across 4 files) are unit-style with direct instantiation + mocking. Zero use of `app.run_test()` or `Pilot`.
- Dependencies `3642` (slash commands), `d869` (escape interrupt), and `3b76` (auto-turn) are all **closed** — slash, interrupt, and auto-turn coverage are in-scope now.
- CI currently runs `uv run pytest`; integration test runtime must remain explicit and controllable.

## Council Input (council-c86e)

**Consensus across all members:**
- `app.run_test()` + `Pilot` harness in `tests/test_tui_integration.py`
- Mock the Council (API calls), not the poller (real file I/O is fast and exercises the real poll→render cycle)
- Gate behind pytest marker from day one, not as a later phase
- Bounded `wait_until()` helper with retries — never fixed sleeps
- Session-isolation regression case is important

**Timing strategy (Claude):** Call `await app.poll_updates()` directly in tests after writing files, bypassing the 100ms timer. Trades purity for determinism — the #1 killer of Textual integration suites is timing flakiness.

**Scope calibration (Claude):** Start minimal (3-4 core scenarios), prove the harness works, then expand. Defer layout-at-multiple-sizes (low value, high maintenance) and visual/snapshot testing.

**Scope expansion (Codex):** Since all deps are closed, slash/interrupt/auto-turn integration coverage should be included now, not deferred.

**Adopted approach:** Start with core scenarios to prove the harness, then immediately expand to slash/interrupt/auto-turn in the same ticket. No multi-phase gating.

## Scope

- Mock Council that writes canned response files to the thread dir (simulates stream start/deltas/final, timeout/error, terminable process).
- `wait_until(predicate, ...)` helper using `pilot.pause()` loops with bounded retries.
- Direct `await app.poll_updates()` calls in tests after writing files (bypass timer for determinism).
- Gate all integration tests behind `@pytest.mark.textual_integration` + `--run-textual-integration` flag from the start.
- **Out of scope:** layout testing at multiple terminal sizes, visual/snapshot testing.

## Test Scenarios

### Core (prove the harness)

1. App boots: header content, input focus, history renders from thread files
2. Keyboard: Enter sends, Shift+Enter inserts newline
3. Send lifecycle: king message appears, waiting panels mount for targets
4. Stream lifecycle: waiting → streaming → finalized via poll + stream file writes
5. Error lifecycle: error body renders `ErrorPanel` with timeout labeling
6. External updates: message files written while app runs appear without restart

### Behavioral (now that deps are closed)

7. Slash commands: `/help`, `/mute`, `/unmute`, unknown command, `/quit`
8. Escape interrupt: active queries terminate, interrupted state rendered, second Escape forces exit
9. Auto-turn: one deterministic auto-turn follow-up cycle

### Regression

10. Fresh thread isolation: `kd chat --new` does not inherit prior session context
11. Speaker label sanitization: persisted bodies do not contain duplicated prefixes (`codex: codex:`)

## Implementation

1. Create `tests/test_tui_integration.py` with fixtures:
   - `tmp_branch_env`: builds temp branch/thread with deterministic members/messages
   - `mock_council`: patches `Council.create` to return fake members that write canned files
   - `wait_until(predicate, pilot, *, timeout=2.0, interval=0.05)`: bounded polling helper

2. Wire pytest gating in `conftest.py` / `pyproject.toml`:
   - Marker: `textual_integration`
   - Flag: `--run-textual-integration`
   - Default `pytest` skips these; full run is opt-in

3. Implement scenarios 1-6 first, verify harness is solid, then 7-11.

## Done Criteria

- [x] Integration tests exist using `app.run_test()` + `Pilot` covering scenarios 1-11.
- [x] All tests gated behind `--run-textual-integration` flag.
- [x] Test suite runs deterministically in ≤30s on local dev machine.
- [x] Test run instructions documented (fast local vs full integration).
- [x] Manual smoke-check of `kd chat` after any CLI/output changes.

## Worklog

- 2026-02-16: Implemented all 11 scenarios (22 tests) in `tests/test_tui_integration.py`:
  - Pytest gating: `@pytest.mark.textual_integration` marker + `--run-textual-integration` flag in `conftest.py`/`pytest.ini`
  - Added `pytest-asyncio` dep with `asyncio_mode = auto` in pytest.ini
  - Harness: `FakeMember` writes canned stream files, `wait_until()` bounded polling helper
  - Core (1-6): boot/header/focus/history, keyboard, send lifecycle, stream→finalized, error panels, external updates
  - Behavioral (7-9): slash commands (/help /mute /unmute /quit unknown), escape interrupt (first=terminate, second=exit), auto-turn sequential round-robin
  - Regression (10-11): session_id cleared after query, no duplicated speaker prefix in persisted bodies
  - 22 tests pass in ~4s, full suite (882 tests) in ~20s
  - Without flag: all 22 integration tests skip cleanly
