---
from: codex
to: king
timestamp: 2026-02-15T02:42:34Z
---

Using the `kingdom` skill for this pass because you’re asking for a design-vs-ticket workflow audit. I’ll first pull `kd design` and `kd tk list`, then drill into each ticket to check coverage, scope, and ordering against the design.
I have the current design and ticket index. Next I’m reading the ticket bodies to compare actual acceptance criteria against the design phases and identify scope drift, missing work, and simplification opportunities.
I’ve pulled all open ticket bodies; I’m now checking the closed tickets referenced in the design so I can call out any stale scope or reopened risks accurately.
**Verdict**
The ticket set is directionally aligned, but it is not fully aligned with the current design. The biggest gaps are Phase 3 coverage and config/state plumbing needed to make Phase 1/2 reliable.

**What Matches**
1. `e756` matches the design’s streaming foundation well.
2. `6412`, `a9c9`, `70f6`, `a4f5`, `d09d`, `3e60` map to the CLI/TUI UX goals.
3. Closed tickets `549b`, `520a`, `41fb` are consistent with design history.

**Where Design And Tickets Diverge**
1. Phase 3 is under-ticketed.
- Design includes auto-mode group chat, round-robin turns, interrupt behavior, and `council.chat` config.
- No ticket explicitly covers orchestration semantics for auto-rounds; `3e60` is too broad and only asks for basic chat UI.

2. Config schema work is missing as a first-class ticket.
- Current config rejects unknown `council` keys (`src/kingdom/config.py:98`, `src/kingdom/config.py:174`).
- Design requires `council.chat` and `council.auto_commit`; only `1e3d` mentions auto_commit, nothing cleanly covers `council.chat`.

3. Status requirements are harder than ticket text suggests.
- `a9c9` says status derived from logs/process state, but council async currently does not persist worker PID/state for status (`src/kingdom/cli.py:459`, `src/kingdom/council/worker.py:24`).
- `thread_response_status` is message-based only (`src/kingdom/thread.py:340`), so “running/interrupted/timed out” cannot be robust without new runtime metadata.

4. `70f6` acceptance conflicts with current design wording.
- Ticket says `--last N` messages.
- Design now uses turn-based thinking in multiple places; this should be unified.

5. `a4f5` assumes “error field” from thread files, but thread messages have no structured error metadata (only markdown body) (`src/kingdom/thread.py:218`).

**Missing Tickets**
1. `council` config schema extension and validation.
- Add `council.chat` (mode, rounds, interrupt policy, etc.) and `council.auto_commit`.
- Update validation/constants in `src/kingdom/config.py`.

2. Council async run-state persistence.
- Persist per-thread/per-round runtime state (started_at, worker pid, members, status transitions) so `a9c9` and `6412` can be reliable.

3. Phase 3 orchestration ticket(s).
- Round-robin auto-mode engine.
- User-interrupt semantics (“queue vs cancel”).
- Stop conditions and round caps.

4. Shared stream normalization layer ticket.
- Reusable by both `watch` and `kd chat`, not duplicated in TUI code.

**Potentially Unnecessary / Should Be Deferred**
1. `1e3d` (auto-commit) is not core to “make council feel natural.”
- It adds git-side effects and failure modes.
- Recommend deferring until after streaming/status/chat are stable, or making default `off`.

2. `41fb` is already closed and effectively done; no further planning weight needed.

**Easier Path**
1. Split work into a strict sequence:
- Foundation: `e756` + config schema + async run-state metadata.
- CLI UX: `6412`, `a9c9`, `70f6`, `d09d`, `a4f5`.
- TUI v1: `3e60` basic chat (broadcast + `@member` + streaming).
- TUI v2: group chat auto-mode (new ticket).

2. Narrow `3e60` to v1 only.
- Keep it to “interactive chat + persisted thread + live stream panels.”
- Move auto-mode/group chat to separate ticket(s).

3. Clarify `70f6` now.
- Decide whether pagination is message-based or turn-based and enforce that everywhere (`show`, `list`, status summaries).

**Recommended Ticket Changes**
1. Update `70f6` acceptance to explicitly choose messages or turns.
2. Update `a9c9` to require explicit runtime metadata source, not “logs and/or process state” handwave.
3. Update `a4f5` to avoid requiring nonexistent “error field” unless a structured metadata ticket is added.
4. Re-scope `3e60` to Phase 2 only; create a new Phase 3 ticket for auto-mode orchestration.
5. Add a new P1 ticket: config schema for `council.chat` + `council.auto_commit`.
6. Add a new P1 ticket: council async run-state persistence (pid/state/round metadata).

If you want, I can draft a concrete “ticket edits/additions” checklist keyed by ticket ID so you can apply it directly.
