---
from: codex
to: king
timestamp: 2026-02-13T19:28:18Z
---

I’ll inspect `git diff HEAD~2..HEAD -- src/` first, then trace each of the three lifecycle changes in code to identify bugs/edge cases and check whether tests cover them.
I’ve got the exact `src` diff. Next I’m checking surrounding command behavior and any test changes in the same commits to identify regressions and coverage gaps for these new flows.
I’ve identified a likely compatibility bug in `tk pull` (legacy run path handling) and I’m quickly validating CLI parsing/edge behavior (`tk pull` with no IDs) before finalizing the review.
**Findings**

1. `P1` `kd tk pull` breaks legacy-run compatibility by always moving into `.kd/branches/...`, even when the active run is legacy `.kd/runs/...`.
`resolve_current_run` explicitly supports legacy runs, but `ticket_pull` hardcodes `branch_root(...) / "tickets"`.
`src/kingdom/cli.py:2321`
`src/kingdom/cli.py:2326`
`src/kingdom/state.py:370`

2. `P2` `kd tk pull` can partially apply moves on multi-ID input, then fail mid-command, leaving mixed state.
The loop moves tickets one-by-one and exits on first error; there is no prevalidation pass.
`src/kingdom/cli.py:2329`
`src/kingdom/cli.py:2337`
`src/kingdom/cli.py:2346`

3. `P2` `kd tk pull` lookup is global (`branches + backlog + archive`), so partial IDs can fail as ambiguous even when backlog contains the intended ticket.
This is because it uses `find_ticket(base, tid)` instead of a backlog-scoped lookup.
`src/kingdom/cli.py:2331`
`src/kingdom/ticket.py:275`
`src/kingdom/ticket.py:327`

4. `P2` Test coverage is missing for all three new lifecycle behaviors.
No test files changed in `HEAD~2..HEAD`, while behavior changed in create/close/reopen/pull paths.
`src/kingdom/cli.py:1974`
`src/kingdom/cli.py:2007`
`src/kingdom/cli.py:2176`
`src/kingdom/cli.py:2183`
`src/kingdom/cli.py:2313`

**Edge-case notes**

1. `kd tk create` path-on-stdout + warning-on-stderr looks correct for command substitution and is an improvement.
`src/kingdom/cli.py:1974`
`src/kingdom/cli.py:2007`

2. Backlog close/reopen move logic behaves as intended in the normal path (backlog -> archive/backlog on close, reverse on reopen).
`src/kingdom/cli.py:2176`
`src/kingdom/cli.py:2183`

**Missing tests to add**

1. `tk create` prints absolute path on stdout and priority clamp warning goes to stderr.
2. `tk close` moves backlog ticket to `.kd/archive/backlog/tickets/`; branch ticket does not move.
3. `tk reopen` restores archived backlog ticket to `.kd/backlog/tickets/`.
4. `tk pull` single and multi success cases; no-active-run, not-found, not-in-backlog, ambiguous-ID failures.
5. `tk pull` transactional expectation (either prevalidate all IDs or explicitly document partial-apply behavior).
