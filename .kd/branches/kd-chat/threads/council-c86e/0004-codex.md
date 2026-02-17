---
from: codex
to: king
timestamp: 2026-02-16T21:27:25Z
---

I’ll use the `kingdom` skill for this since it’s a ticket-planning workflow. I’m going to inspect ticket `cf1a` and related context with read-only commands, then propose a concrete integration-test plan for discussion.
I’ve loaded the `kingdom` workflow instructions and confirmed `kd tk show` is the right read-only command. Next I’m pulling ticket `cf1a` details and any dependencies to ground the plan in the actual acceptance criteria.
I’ve read `cf1a`; it already has broad scope, but not the concrete implementation slices yet. I’m now checking dependency tickets `3642` and `d869` plus current TUI test structure so we can propose a realistic, staged execution plan.
Both dependency tickets are already closed, so slash and escape coverage can be included immediately rather than deferred. I’m now reading `ChatApp` and current TUI tests to convert `cf1a` into concrete test files, fixtures, and scenario order.
I confirmed the current tests are still mostly unit-level and mocked; there’s no real `app.run_test()` coverage yet. I’m now checking pytest config and helper utilities so the plan includes exact marker/flag wiring and fixture reuse.
I’ve confirmed the app and poller paths that integration tests need to exercise. I still need one quick pass over CLI/test config to pin down how to implement `--run-textual-integration`; I’m rerunning that lookup with safer commands.
There are currently zero `run_test()`/`Pilot` tests in the repo, so this is a fresh integration harness effort. I’m pulling `format_thread_history` and related formatting logic next, because `cf1a` also calls out session-isolation and duplicated speaker labels as regression cases.
I found one important update for planning: `cf1a` still says slash/interrupt tests are “after dependencies land,” but both dependencies are already closed. I’m checking `3b76` status quickly so we can decide whether to include auto-turn coverage now or keep it explicitly out-of-scope.
`3b76` is also closed, so auto-turn integration coverage is now feasible too. I’m making one last context pass on `Council`/member query seams to ensure the plan is implementable without flaky external subprocesses.
I have enough context to propose a concrete execution plan. I’ll keep it implementation-level (test names, fixtures, gating, order), and call out scope corrections in `cf1a` based on current ticket status.
I also checked existing assertions around speaker-prefix stripping and found it only removes one leading `name:` today; duplicated prefixes can still leak through. I’m now drafting the plan to include that as a targeted regression case (and likely tiny behavior fix) under this ticket’s scope.
`cf1a` needs tightening, but it’s workable. Concrete plan I’d execute:

1. **Re-scope `cf1a` based on current state (as of February 16, 2026).**
- `3642` (slash commands), `d869` (escape interrupt), and `3b76` (auto-turn) are already closed.
- So slash/interrupt/auto-turn integration coverage should be **in-scope now**, not “pending.”

2. **Build one deterministic integration harness first (`app.run_test()` + `Pilot`).**
- New module: `tests/test_tui_integration.py`.
- No real agent subprocesses; patch `Council.create` to return fake members that simulate:
  - stream start/deltas/final message,
  - timeout/error,
  - long-running query with terminable `process`.
- Add `wait_until(...)` helper using `pilot.pause()` loops (bounded retries, no fixed sleeps).

3. **Implement baseline UI-flow cases (real TUI driving).**
- Boot/history/focus.
- Enter sends; Shift+Enter inserts newline.
- Waiting → streaming → finalized panel transitions.
- Error body renders `ErrorPanel` with timeout labeling.
- External message file updates appear without restart.
- Layout sanity at `80x24` and one wider size.

4. **Add behavioral integrations now that deps are closed.**
- Slash commands: `/help`, `/mute`, `/unmute`, unknown command, `/quit`.
- Escape interrupt: active queries terminate, interrupted state rendered, second Escape forces exit.
- Auto-turn follow-up flow: sequential round-robin behavior for deterministic budget.

5. **Add two regression tests called out in ticket notes.**
- Fresh/new chat thread does not inherit prior thread/session context.
- Persisted message body is sanitized against duplicated speaker labels (e.g. `codex: codex:`).

6. **Gate these tests behind explicit opt-in.**
- Marker: `textual_integration`.
- Flag: `--run-textual-integration`.
- Default `uv run pytest` remains fast; full run opt-in.

7. **Define done criteria for this ticket.**
- Integration suite passes deterministically under flag.
- Runtime target documented (e.g. <= ~30s on local dev machine).
- README/testing docs include exact commands for fast vs full runs.

Main tradeoff: keep integration tests at TUI/file-poller boundary only; don’t test external model CLIs here. That keeps coverage high and flakiness low.
