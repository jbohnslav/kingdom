---
from: codex
to: king
timestamp: 2026-02-13T22:49:11Z
---

I’ll locate the backlog cleanup design doc first using `kd design`, then I’ll read it and return a risk-focused review with concrete recommendations and ordering feedback.
I found the design doc path and next I’m reading it with line numbers so I can reference specific sections in the review.
I’ve read the design and I’m now sampling the current implementation paths it references (council ask/watch, ticket resolution, done flow) to validate whether the proposed fixes match reality.
I’m drilling into the actual command implementations now to check whether the design assumptions are already true or need adjustment, especially around council targeting, ticket IDs, and `kd done`.
I found some immediate mismatches with the design assumptions; I’m now validating them in `watch_thread`, `_resolve_peasant_context`, and `done` before I give you concrete findings.
I confirmed current behavior differs from several proposed items (for example `council ask` is async by default, and `CLAUDE.md` lacks timeout config). I’m checking the tests next to see what behavior is intentionally locked in.
I’ve confirmed there’s no mention parser or assignment commands today; next I’m checking `tk create/list` details and the branch-protection workflow impact before final recommendations.
I’m validating whether `kin-d5ae` is really “verification only” by checking peasant/work tests for backlog auto-pull behavior and edge cases.
I found a key modeling gap: `tk move` variadic IDs are ambiguous with today’s positional `target`, and council watch targeting should key off the latest ask message (not thread members). I’m confirming that from the thread model now.
I’ve gathered enough static evidence; I’m running a few focused tests to confirm whether the “already implemented” items are actually passing in this branch.
1. **High:** Ticket ID migration is under-scoped and likely to break behavior as written.
`design.md` treats this as mostly “generation + display” plus file renames (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:44`, `.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:101`), but current code hardcodes `kin-` in core flows (`src/kingdom/ticket.py:72`, `src/kingdom/ticket.py:88`, `src/kingdom/cli.py:2343`).
Risk: renamed files without rewriting frontmatter IDs/deps/parent refs will create inconsistent IDs and lookup surprises.

2. **High:** `tk move` “variadic IDs” is ambiguous with the current positional CLI shape.
Design says extend `tk move` like `tk pull` (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:50`), but current signature is `tk move <ticket_id> [target]` (`src/kingdom/cli.py:2275`).
You need a syntax redesign (for example `tk move --to <target> <id>...`) before implementing multi-ID move.

3. **High:** Council watch targeting fix is only partially modeled.
Design says pass `expected` from ask (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:27`) and that is already implemented (`src/kingdom/cli.py:438`, `src/kingdom/cli.py:439`).
But `kd council watch` without explicit `expected` still falls back to thread members (`src/kingdom/cli.py:591`), which can mismatch targeted follow-ups on mixed-member threads.

4. **Medium:** Timeout proposal has a no-op/confusing piece.
Design says “increase default council timeout from 300s to match” (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:31`), but default is already 300s (`src/kingdom/cli.py:289`).
`CLAUDE.md` update is valid and currently missing (`CLAUDE.md:1`), but units/intent should be clarified in the doc.

5. **Medium:** `kd done` auto-commit as default has workflow risk.
Current `done` only moves files and updates state (`src/kingdom/cli.py:193`, `src/kingdom/cli.py:246`).
Making commit default can accidentally include unrelated staged work unless you enforce strict staging + clean-tree guards.

6. **Medium:** Design-approved frontmatter is not “simple” in this codebase.
Design proposes design.md frontmatter status (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:61`), but current behavior uses `state.json` (`src/kingdom/cli.py:786`) and `kd status` reports doc presence, not approval state (`src/kingdom/cli.py:1805`).
This is feasible, but it’s a schema shift, not just a small field add.

7. **Low / scope hygiene:** Several tickets are already implemented or mostly done.
`kin-c749` behavior is present (`src/kingdom/cli.py:438`), `kin-d5ae` auto-pull is present (`src/kingdom/cli.py:1015`), and `tk pull` already supports multiple IDs (`src/kingdom/cli.py:2321`).
I ran targeted tests and they pass: `tests/test_cli_ticket.py::TestTicketPull`, `tests/test_cli_peasant.py::TestBacklogAutoPull`, and a council watch targeted test (15 passed total).

**Execution Order Recommendation**
1. Reclassify/close “already done” tickets first (verification-only pass).
2. Do branch protection earlier (after confirming PR path), not last.
3. Ship council behavior changes (`db3b`, `b43e`, `09c9`) together.
4. Do assignment + `tk move` syntax redesign together.
5. Do `kd done` commit behavior after explicit policy decision.
6. Keep ID migration (`kin-98e7`) isolated in its own PR/batch due blast radius.

**Open Questions**
1. Migration trigger: prefer explicit `kd migrate ticket-ids --dry-run/--apply`, not automatic on next invocation.
2. `@all`: yes, support it; make it override specific mentions, and fail loudly on unknown mentions.
3. `kd done` auto-commit default: start opt-in (`--auto-commit`) first; only consider default later with clean-tree/staging safeguards.
