---
id: "cf1a"
status: open
deps: [3642, d869]
links: []
created: 2026-02-16T11:21:29Z
type: task
priority: 2
---
# Extensive Textual integration tests for kd chat (with optional slow-test flag)

Build deeper end-to-end integration coverage for `kd chat` using Textual's test harness (`app.run_test()` + `Pilot`) so we verify real UI behavior, not only unit-level methods.

## Current State (2026-02-16)

- Existing TUI tests are mostly unit-style (`tests/test_tui.py`, `tests/test_tui_poll.py`, `tests/test_tui_widgets.py`) and do not drive the app through `app.run_test()` + `Pilot`.
- `ChatApp` currently has core send/poll/render behavior, but slash commands and escape-interrupt semantics are tracked in separate open tickets:
  - `3642` slash commands (`/mute`, `/unmute`, `/help`, `/quit`)
  - `d869` escape interrupt and subprocess termination behavior
- CI currently runs `uv run pytest`; integration test runtime must remain explicit and controllable.

## Scope

- Add Textual integration tests that drive real user flows (typing, Enter, Shift+Enter, key bindings, and command submission).
- Cover implemented chat flows now: thread history render, send flow, waiting/streaming/finalized transitions, error rendering, and external updates visible in the running TUI.
- Cover slash/interrupt flows in this ticket once the dependent behavior lands (`3642`, `d869`) using the same integration harness.
- Use async-friendly checks (`pilot.pause()` / bounded waits) so tests assert post-update UI state reliably.
- Run selected scenarios at multiple terminal sizes (at least `80x24` and one wider layout) to catch layout regressions.
- Optionally add visual/snapshot checks only if deterministic and low-noise.

## Execution Plan

### Phase 1: Harness + Baseline Integration Coverage (can start now)

- Create a dedicated integration module (for example `tests/test_tui_integration.py`) focused on real Textual app driving.
- Add test helpers/fixtures to:
  - build a temporary branch/thread with deterministic members/messages
  - start `ChatApp` under `app.run_test()`
  - poll the UI safely (small bounded waits instead of fixed sleeps where possible)
  - inspect mounted widget state by id/class (`MessagePanel`, `WaitingPanel`, `StreamingPanel`, `ErrorPanel`)
- Implement baseline integration scenarios:
  - app boot: header content, input focus, history render from thread files
  - keyboard input: Enter sends, Shift+Enter inserts newline
  - send lifecycle: king message appears immediately, waiting panels mount for targets
  - stream lifecycle: waiting -> streaming -> finalized via real poll loop and stream file updates
  - error lifecycle: error body renders `ErrorPanel` with timeout labeling
  - external updates: new message files written while app runs appear without restart
  - layout sanity at two terminal sizes

### Phase 2: Slow-Test Gate + Documentation

- Add an explicit marker and CLI gate for the integration suite:
  - marker name: `textual_integration`
  - CLI flag: `--run-textual-integration`
- Wire gate in test config (`conftest.py` / `pytest.ini`) so these tests skip unless explicitly enabled.
- Document commands for fast vs full runs:
  - default fast run
  - full integration run with the new flag
  - CI guidance for where/when to enable the full suite

### Phase 3: Pending Feature Coverage (after dependencies land)

- Add integration cases for slash commands once `3642` is complete.
- Add integration cases for escape interrupt behavior once `d869` is complete.
- If auto-turn behavior from `3b76` lands during this work, extend integration scenarios to cover one deterministic auto-turn cycle.

## Test Matrix

- Startup:
  - existing history is rendered in order
  - no-history thread starts cleanly
- Input:
  - Enter submits
  - Shift+Enter preserves multiline input
  - `@member` targeting affects waiting panels / dispatch fanout
- Streaming:
  - start event replaces waiting panel
  - deltas update streaming content
  - final message removes streaming panel and mounts finalized panel
  - timeout/error messages produce `ErrorPanel`
- Runtime updates:
  - thread files updated externally are reflected while app is open
- Layout:
  - base layout remains usable at `80x24`
  - wider terminal layout keeps header/log/input visible and non-overlapping

## Risks / Decisions

- Determinism: avoid brittle timing assertions; prefer bounded retry/pause polling helpers.
- Plugin choice: avoid adding new pytest plugins unless necessary; use `asyncio.run(...)` wrappers if that keeps the setup simpler.
- Snapshot testing remains optional; only adopt if output is stable across environments.

## Diagnosis Notes (2026-02-16)

Observed in live thread `council-9cb6`:

- `0004-cursor.md` and `0007-cursor.md` contain "Council Advisor" meta-analysis instead of normal in-thread recall.
- Later turns now ingest those messages via `format_thread_history(...)`, so the meta style is reinforced in subsequent prompts.
- The same thread also shows agent-label duplication (`codex: codex: ...`) in stored bodies, which further pollutes history context.

Root-cause hypothesis (code-level):

- `kd chat` currently uses `CouncilMember` query path, which prepends council-advisor framing for every query.
- `ChatApp.on_mount()` also calls `self.council.load_sessions(...)`, so branch-level resume IDs can leak prior context into new chat threads.
- With full-history injection enabled, any off-style/meta response becomes durable context and compounds over turns.

Implications for this integration-test ticket:

- Add integration coverage that verifies behavior in a fresh thread with no pre-existing session context.
- Add a session-isolation regression case: a new `kd chat --new` thread should not inherit unrelated prior-agent context.
- Add transcript-sanitization assertions so speaker labels are not duplicated in persisted message bodies.

## Acceptance Criteria

- [ ] New Textual integration tests exist using `app.run_test()` + `Pilot`.
- [ ] Baseline implemented chat flows are covered by integration tests (startup, input, streaming, error, external updates, basic layout).
- [ ] Integration tests can be explicitly included/excluded via pytest flag/marker gating.
- [ ] Test run instructions are documented (fast local run vs full integration run).
- [ ] Slash/interrupt integration coverage is added in this ticket once `3642` / `d869` behavior is available.
- [ ] `kd chat` behavior is manually smoke-checked after any CLI/output interaction changes.
