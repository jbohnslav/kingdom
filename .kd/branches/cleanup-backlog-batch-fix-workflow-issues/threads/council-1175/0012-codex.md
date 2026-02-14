---
from: codex
to: king
timestamp: 2026-02-13T23:41:06Z
---

I’ll re-read that design doc and then audit the listed implementation files line-by-line against it, including migration/backward-compat paths and test coverage gaps.
I’ve re-read the updated design and part of `cli.py`; next I’m checking the migration implementation and done-branch filtering paths, then the specified tests for coverage gaps.
I’ve located the migration and lifecycle code; now I’m reviewing `ticket.py` plus the exact tests you listed to identify mismatches and missing cases before merge.
I’m now validating with the relevant test files directly to catch any regressions or mismatches that static review may miss, especially around migration and ID compatibility.
`uv` cache access is blocked in this sandbox, so I’m switching to the repo venv Python directly for command-level checks.
I’ve identified several concrete mismatches and am doing one final pass on compatibility details (like timeout config and legacy ID handling) before I give you merge-blocking vs non-blocking recommendations.
1. **High: done-branch filtering is incomplete, so “done” branches still affect normal ticket resolution.**
`find_ticket` still searches all branches and archive unconditionally (`src/kingdom/ticket.py:313`, `src/kingdom/ticket.py:327`), while the design requires done branches to be hidden by default (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:82`, `.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:107`).
Impact: ambiguity and accidental edits on done-branch tickets from commands that call `find_ticket`.

2. **High: migration is destructive by default, contrary to the design’s explicit opt-in.**
Design calls for explicit `--dry-run`/`--apply` flow (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:62`, `.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:144`).
Implementation applies changes on plain `kd migrate` (`src/kingdom/cli.py:1973`, `src/kingdom/cli.py:1975`). That is risky.

3. **High: migration rename path can clobber files and does not enforce safe preflight.**
Renames use `Path.rename()` directly (`src/kingdom/cli.py:2016`) with no collision check against existing short-name files.
Also diverges from “use `git mv`” requirement (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:58`, `.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:103`).

4. **Medium: @mention parser misses stated edge-case requirements.**
Design says avoid false positives in code blocks and fail on unknown mentions (`.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:46`, `.kd/branches/cleanup-backlog-batch-fix-workflow-issues/design.md:147`).
Current regex is global (`src/kingdom/cli.py:313`) and `@all` path bypasses unknown validation (`src/kingdom/cli.py:315`).

5. **Medium: `tk move` backward-compat heuristic is fragile.**
The 2-arg compatibility logic infers whether arg2 is a target by searching tickets (`src/kingdom/cli.py:2457`), so branch names that look like ticket IDs can be misinterpreted.

6. **Medium: migration/back-compat test coverage gap.**
No tests in the reviewed set exercise `migrate` behavior/collisions/opt-in semantics, and no tests validate done-branch exclusion in `find_ticket`-based commands.
Reviewed tests pass (`tests/test_cli_council.py`, `tests/test_done.py`, `tests/test_ticket.py`), but these risks are currently untested.

**Design-match summary**
- Implemented and aligned: sync-by-default council + `--async` (`src/kingdom/cli.py:281`), status-only `kd done` (`src/kingdom/cli.py:203`), assignee commands (`src/kingdom/cli.py:2397`), `status` showing `design_approved` (`src/kingdom/cli.py:1873`), `tk move` multi-ID + `--to` (`src/kingdom/cli.py:2444`).
- Partially aligned / divergent: migration flow semantics and safety; global done-branch filtering.

**Fix before merge**
1. Make migration explicit opt-in (`--apply` required; default dry-run).
2. Add migration preflight: collision detection + abort on conflicts.
3. Decide and enforce default exclusion of done branches in `find_ticket` call paths.
4. Tighten @mention parsing to satisfy the code-block/unknown rules.
5. Add focused tests for 1-4 before merge.
