---
from: codex
to: king
timestamp: 2026-02-13T17:46:41Z
---

I’ll validate each listed PR finding against the current code state and call out which ones are still true, outdated, or misframed, with file/line evidence. I’m starting by checking the exact implementations for worktree paths, message sequencing, backlog auto-move, and `kd work --base`.
I’m going to validate each of the listed review findings against the current unstaged code and then give a yes/no call per item with any extra issues I see. I’ll stay read-only and cite concrete file/line references.
I’ve confirmed several issues directly in `cli.py`/`thread.py`; next I’m checking the remaining items (`council_watch`, `ticket edit`, `state`, preamble/env handling) and then I’ll run the targeted test files to confirm which gaps are still active.
I’ve validated most code-level items; I’m now running the two affected test modules to verify the integration status and whether the previously reported failures are now resolved.
I’ve run the targeted tests and checked each PR finding against the current code. Next I’ll give you a strict status per finding (agree/disagree) plus a short list of additional fixes that are not in the PR notes.
**Findings (current code, ordered by severity)**

1. `Agree` with #1: worktrees are created under `.kd/worktrees` inside repo (`src/kingdom/cli.py:870`), which is risky/invalid for git worktrees.
2. `Agree` with #2: message numbering is non-atomic (`src/kingdom/thread.py:249`, `src/kingdom/thread.py:277`), so concurrent writers can collide.
3. `Agree` with #3: backlog auto-move is in `_resolve_peasant_context` (`src/kingdom/cli.py:1001`), and that function is used by read commands like logs/stop (`src/kingdom/cli.py:1243`, `src/kingdom/cli.py:1286`).
4. `Agree` with #4: reject path falls back to base when worktree missing (`src/kingdom/cli.py:1551`).
5. `Agree` with #5: `council_watch` uses thread members metadata, not current ask target (`src/kingdom/cli.py:594`).
6. `Agree` with #6: `--hand` allows parallel workers on same checkout; guard is per-session/ticket only (`src/kingdom/cli.py:1086`).
7. `Agree` with #7: naive `created` parsing can produce mixed naive/aware datetimes (`src/kingdom/ticket.py:134`, `src/kingdom/ticket.py:261`).
8. `Agree` with #8: `normalize_branch_name` can return empty string (`src/kingdom/state.py:26`).
9. `Agree` with #9: council preamble says run `kd design` (`src/kingdom/council/base.py:42`), and `kd design` can create files.
10. `Agree` with #10: watch timeout boundary can miss responses at edge (`src/kingdom/cli.py:627`).
11. `Partial` on #11: `_resolve_peasant_context(..., base=...)` is fixed (`src/kingdom/cli.py:1683`), but interactive `kd work` still uses `Path.cwd()` for worktree (`src/kingdom/cli.py:1687`). Bug or intended behavior depends on your `--base` semantics.
12. `Agree` with #12: `$EDITOR` flags still break because it runs `[editor, file]` (`src/kingdom/cli.py:2345`).
13. `Agree` with #13: temp filename is PID-only (`src/kingdom/state.py:149`), despite comment claiming more uniqueness.
14. `Disagree / stale` on #14: `.github/workflows/codex.yml` is not present in this tree.
15. `Agree` with #15: reused thread + expected members logic can terminate watch too early (`src/kingdom/cli.py:594`, `src/kingdom/cli.py:641`).

**Additional issues not in that list**

1. `_resolve_peasant_context` uses global `find_ticket` across all branches/backlog/archive (`src/kingdom/cli.py:983`, `src/kingdom/ticket.py:275`), so it can resolve a ticket from the wrong branch.
2. If you fix #1 (external worktree location), path assumptions are duplicated in multiple places (`src/kingdom/cli.py:938`, `src/kingdom/cli.py:1361`, `src/kingdom/cli.py:1551`), so centralize worktree path resolution first.

**Status against kin-10ee top integration gaps**

1. The originally mentioned `test_cli_peasant`/`test_council` failures are resolved now: `uv run pytest tests/test_cli_peasant.py tests/test_council.py -q` passed (`88 passed`).
2. `launch_work_background` extraction exists (`src/kingdom/cli.py:1014`), interactive thread seeding exists (`src/kingdom/cli.py:1694`), and dead code cleanup appears done (no `harness.py` main entrypoint; no empty `kd agent` group).
