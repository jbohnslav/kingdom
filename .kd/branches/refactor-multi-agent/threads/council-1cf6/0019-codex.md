---
from: codex
to: king
timestamp: 2026-02-09T18:56:25Z
---

I’ll compare `design.md` against the three new tickets and call out any remaining gaps or unstated risks, with findings ordered by severity.
I’m checking related open tickets for overlap/conflicts so I can tell you what’s truly still missing versus already captured elsewhere.
1. **Missing: explicit worktree bootstrap ticket (`uv sync` + `pre-commit install` on `kd peasant start`).**  
Design requires this at startup (`.kd/branches/refactor-multi-agent/design.md:273`), and `kin-41f9` showed it was a real failure (`.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:108`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:109`).  
Your three new tickets only cover logging/gates, reject-relaunch/warnings, and sync; startup bootstrap is still untracked.

2. **Missing: formal “done gate parity” definition (what exact commands define DONE).**  
`kin-9a32` adds `pytest + ruff check` (`.kd/branches/refactor-multi-agent/tickets/kin-9a32.md:29`), but smoke test feedback included formatting/pre-commit drift (`.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:109`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:111`).  
You should add one explicit contract ticket (or extend `kin-9a32`) stating whether DONE requires `ruff format --check` and/or `pre-commit run --all-files`, not just `ruff check`.

3. **Missing: “restart ergonomics” ticket/acceptance (`kd peasant restart` alias or equivalent).**  
This pain is called out directly (`.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:105`).  
`kin-cebe` helps by auto-relaunch on reject, but does not address explicit manual restart UX.

4. **Missing: design/ticket state reconciliation for council work.**  
Council fixes are apparently done, but T4 is still fully unchecked in design (`.kd/branches/refactor-multi-agent/design.md:402`).  
If implementation is merged, add a doc/ticket hygiene task to mark what’s complete and remove conflicting old text (interactive default vs async-first guidance at `.kd/branches/refactor-multi-agent/design.md:248` and `.kd/branches/refactor-multi-agent/design.md:255`).

5. **Minor inconsistency: priority metadata drift.**  
You listed P1/P2/P3, but all three new ticket files currently have `priority: 1` (`.kd/branches/refactor-multi-agent/tickets/kin-9a32.md:8`, `.kd/branches/refactor-multi-agent/tickets/kin-cebe.md:8`, `.kd/branches/refactor-multi-agent/tickets/kin-0360.md:8`).  
Not a blocker, but it will confuse queue ordering.

If you want, I can propose exact acceptance criteria text for the two missing functional items: startup bootstrap and DONE gate parity.
