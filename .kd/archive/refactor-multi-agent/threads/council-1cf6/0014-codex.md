---
from: codex
to: king
timestamp: 2026-02-09T17:54:36Z
---

I’ll review `design.md` together with `kin-41f9` and give a prioritized “what’s next” list grounded in the remaining gaps, with findings first and no code changes.
**Findings (Priority-Ordered)**

1. **Critical: Peasant runtime still has unresolved correctness risks from kin-41f9, despite council progress.**
`kin-41f9` reports stale worktrees, incomplete harness gates, weak logs, and reject-relaunch gaps (`.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:106`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:111`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:107`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:110`).
`design.md` now calls these out, but execution acceptance still mostly sits in T6 (unchecked), so operational reliability is not closed yet (`.kd/branches/refactor-multi-agent/design.md:433`).

2. **High: T3 (session/state) is still entirely open and blocks robust lifecycle behavior.**
All T3 acceptance items are unchecked (`.kd/branches/refactor-multi-agent/design.md:390`).
Without this foundation, dead/alive detection, resume continuity, and status truth remain fragile.

3. **High: Council section has improved direction, but UX contract is still mixed.**
The doc currently carries interactive default, async mode, and prior TUI-backgrounding caveat together (`.kd/branches/refactor-multi-agent/design.md:248`, `.kd/branches/refactor-multi-agent/design.md:251`, `.kd/branches/refactor-multi-agent/design.md:255`).
That ambiguity can reintroduce confusion in CLI behavior.

4. **Medium: Council hardening is described, but T4 is still unchecked across the board.**
If council fixes landed, T4 should be reconciled to reality (`.kd/branches/refactor-multi-agent/design.md:402`).
Right now planning signal is noisy because doc status lags implementation.

5. **Medium: Worktree bootstrap/freshness and message delivery semantics still need explicit acceptance hooks.**
Design text includes `uv sync` / `pre-commit install` and `peasant sync`, plus “warn if not running” for `msg` (`.kd/branches/refactor-multi-agent/design.md:273`, `.kd/branches/refactor-multi-agent/design.md:269`, `.kd/branches/refactor-multi-agent/design.md:437`), but acceptance criteria do not yet prove these invariants end-to-end.

**What’s Next**

1. **Close T4 formally first (doc truth + acceptance checkoff).**
Declare the final council contract (`ask` default behavior, `--async`, `watch/show --wait`, read-only permissions), then mark completed T4 acceptance items.

2. **Do T3 next (state/session completeness).**
Finish `get/set/list` state APIs and `.session` migration so lifecycle/state-driven commands are reliable.

3. **Then finish T6 (supervision loop hardening).**
Prioritize reject auto-relaunch, dead-peasant message warnings, and review workflow behavior.

4. **Add a focused “peasant reliability” acceptance block (or T7).**
Track these explicitly from kin-41f9:
- harness gates match review gates,
- failure logs include actual test/lint output,
- bootstrap guarantees (`uv sync`, `pre-commit install`),
- worktree staleness detection/remediation before done/review.

**Assumption**

- I’m assuming “council fixes” are implemented in code already, and your ask is planning/sequencing from the design doc state.
