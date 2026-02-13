---
from: codex
to: king
timestamp: 2026-02-13T19:21:22Z
---

I’ll review the design doc in `.kd/branches/ticket-management-ux/design.md` first, then cross-check current `kd tk` command behavior in the codebase to validate the decisions and identify gaps, including whether `kd tk pull --all` is warranted.
I have the design doc loaded. Next I’m checking the current `kd tk` implementation paths (`create`, `close`, `move`) so I can validate edge cases and give concrete recommendations against existing behavior.
I found the relevant implementation in `src/kingdom/cli.py` and ticket helpers; I’m pulling exact command logic and tests now to ground the review in current behavior and constraints.
I’ve confirmed where these commands live; now I’m reading the exact `ticket_*` command implementations and related tests to pinpoint behavioral gaps against the design.
I confirmed there are currently no dedicated CLI tests for `kd tk create/close/move`, which affects confidence in these lifecycle changes. I’m now checking help/docs and command patterns to assess compatibility risks (especially stdout expectations).
I found the source tickets for `kin-7402/613d/341e`; there’s an important mismatch with `kin-341e` (it asks for `git mv`) versus this design’s non-goal. I’m verifying docs/current CLI contract next to assess breakage risk.
**Findings (ordered by severity)**

1. `P1` Requirement conflict on move semantics: design says `git mv` is a non-goal, but the source ticket for `kd tk pull` requires it. This will cause acceptance confusion unless reconciled.
` .kd/branches/ticket-management-ux/design.md:47`
` .kd/backlog/tickets/kin-341e.md:18`

2. `P1` “`update_ticket_status` is the single choke point” is not true today, so backlog auto-archive can be bypassed by existing close flows.
` .kd/branches/ticket-management-ux/design.md:36`
` src/kingdom/cli.py:1548`
` src/kingdom/cli.py:2157`

3. `P2` `kd tk pull` behavior is under-specified for multi-ID failures and lookup scope. You should define pre-validation vs partial success, and require active run explicitly.
` .kd/branches/ticket-management-ux/design.md:39`
` .kd/branches/ticket-management-ux/design.md:41`
` src/kingdom/state.py:378`
` src/kingdom/ticket.py:307`
` src/kingdom/ticket.py:327`

4. `P2` `kd tk create` stdout contract needs tighter definition for scripting compatibility. Changing stdout from ID to path can break callers that parse ID; also warnings currently print to stdout.
` .kd/branches/ticket-management-ux/design.md:27`
` .kd/branches/ticket-management-ux/design.md:30`
` src/kingdom/cli.py:1974`
` src/kingdom/cli.py:2007`

5. `P3` Two context statements in the design are stale vs current code (`-d` already optional; `--backlog` list already filters closed). Not blocking, but weakens problem framing.
` .kd/branches/ticket-management-ux/design.md:12`
` .kd/branches/ticket-management-ux/design.md:17`
` src/kingdom/cli.py:1987`
` src/kingdom/cli.py:2022`

**Are the decisions sound?**
Mostly yes: path output for `create`, backlog auto-archive on close, and separate `pull` command are all directionally good. The main gaps are acceptance alignment, choke-point consistency, and precise command semantics.

**Anything missing?**
Define these explicitly:
1. `pull` error model for multiple IDs (fail-fast vs partial).
2. `pull` lookup rule (backlog-only resolution, partial-ID ambiguity handling).
3. `reopen` behavior for archived backlog tickets.
4. stdout/stderr contract and compatibility mode for `create` (`--id` or `--json`).

**Should `kd tk pull` support `--all`?**
Not in v1. Keep explicit IDs for safety and predictability. If added later, require guardrails (`--all --yes`, open tickets only, and clear summary before move).
