# Design: bugfixes-and-minor-features

## Goal
Stabilize kd by fixing all P1 bugs and shipping small P2 improvements — no new major features, just making what exists work better.

## Context
The backlog has accumulated several crash-level bugs in the Chat TUI (color attribute errors in long sessions, crashes on concurrent sends, broken auto-scroll) and peasant workflow (--hand mode exits immediately). There are also a handful of small CLI quality-of-life gaps (no `tk delete`, no `tk undep`, no priority filtering on backlog list, etc.). This branch batches them all into one sweep.

This is the largest branch so far (17 tickets at creation, later expanded to 19). It doubles as a stress test of the kd workflow itself — any friction in the ticket lifecycle will surface quickly.

## Requirements
- Fix all P1 bugs: Chat TUI color crash, auto-scroll, concurrent send crash, peasant --hand
- Ship P1 workflow fix: `kd setup-skill` symlink command (`cb69`)
- Fix P2 bugs: click-inserts-commas, MountError on ErrorPanel, @all broadcast regression
- Add minor CLI features: `tk undep`, `tk delete`, `tk close --duplicate-of`, `tk ready` branch/backlog separation, backlog priority filter, `config show` source indication, peasant sync progress, peasant review no-diff warning, NO_COLOR/TERM=dumb support, slash command discoverability
- Full test suite green after each ticket

## Non-Goals
- Chat TUI Phase 2 or Phase 3 features
- New agent backends (Gemini, OpenCode)
- Integration test infrastructure
- Public repo / release workflow changes

## Resolved: 7e6e (pre-existing test failure)
Closed as already-resolved upstream. The test `test_cursor_assistant_snapshot_chunks_should_use_latest_snapshot` was fixed and rewritten during the `kd-chat` branch (commit `2e057b7`). Replacement tests `test_cursor_snapshot_fresh_after_finalization` and `test_cursor_non_cumulative_fragments_concatenated` both pass. PR #25 merged with full green suite. No pre-existing test failure blocking this branch.

## Work Order

### Phase 0: Code quality baseline
1. **c6b2** — Pythonic deslop. Run the pythonic-deslop style guide across the codebase before any feature work. Clean up AI slop, remove underscore-prefixed functions, simplify over-engineered patterns. This establishes a clean baseline so subsequent diffs are about real changes, not style fixes mixed in.

### Phase 1: Unlock dogfooding
2. **0e8a** — Fix peasant quality gates (wrong Python path, hardcoded to pytest/ruff)
3. **1147** — Fix peasant `--hand` mode. Stale-check first (may be fixed by PR #25 like 7e6e was). If still broken, fix it. Once working, use `--hand` to work remaining tickets — that's the real validation.

### Phase 2: Chat TUI P1 cluster (batch together)
4. **966e** — Crash on send while response in-flight
5. **26ce** — AttributeError on style._color in long sessions (may relate to SSH disconnect/reconnect or terminal reattach — see ticket notes)
6. **0e99** — Auto-scroll broken + duplicate scrollbars

These share a subsystem and likely share context. Work them as a batch rather than interleaving with CLI tickets. If any collapse to the same root cause, close duplicates with a note (or use `--duplicate-of` once f172 ships).

### Phase 3: Remaining P1
7. **cb69** — `kd setup-skill` command to symlink agent skill into the correct directory

### Phase 4: P2 bugs
8. **6e80** — Click inserts extra characters (commas)
9. **5a32** — MountError on ErrorPanel(id='interrupted-codex')
10. **c356** — @all multi-agent broadcast no longer parallel
11. **d0a2** — peasant review should flag no code diff

### Phase 5: P2 CLI features
12. **f172** — `tk close --duplicate-of`
13. **c1c7** — `tk ready` branch/backlog separation
14. **1fa5** — `tk delete`
15. **d739** — `tk list --backlog` priority filter
16. **03b1** — `tk undep`
17. **9cc9** — `config show` source indication
18. **6b95** — Peasant sync progress feedback
19. **98d0** — NO_COLOR / TERM=dumb handling
20. **5243** — Slash command discoverability (e.g. `/writeable` listed in help/discovery surface)

## Execution Policy

### Stale-check P1s before coding
PR #25 (peasant fixes) and the kd-chat branch changed a lot of the same code these bugs touch. Before writing code for any P1, verify it's still broken on this branch. Pattern: run the relevant code path, check for the bug, proceed only if confirmed.

### TUI bug approach: signature-first
The TUI tickets are underspecified (created from real usage where work context can't be shared). But each has a specific enough error signature to work from the code side:
- `26ce`: grep for `_color` attribute access on style objects
- `5a32`: find `interrupted-codex` widget ID and trace mount/unmount lifecycle
- `6e80`: click around in the TUI to reproduce comma insertion
- `c356`: read the `@all` dispatch code and check if it fans out concurrently

Peasants should flesh out ACs during implementation: add concrete repro steps, expected behavior, and regression tests as they discover them.

### TUI stress scenarios
For TUI bugs that are hard to reproduce deterministically:
- Long session / message flood
- Rapid resize + focus churn
- Simulate terminal capability/state changes (for 26ce)
- Click/focus event fuzzing (for 6e80)

### Dogfooding
Fix `--hand` first, then use it to work remaining tickets. Exercise the full ticket lifecycle on every fix: `kd tk start` → work → `pytest` → `kd tk close` → commit `.kd/` changes. With 18 remaining tickets, any workflow friction will surface fast. Run `kd done` at the end to validate it handles a branch with this many closed tickets.

### Duplicate detection
Some TUI bugs may share root causes (especially 26ce and 5a32, both involving stale widget/style state). When two tickets collapse, keep one as primary and close the other as duplicate — use `--duplicate-of` if f172 ships first, otherwise note the relationship manually.

## Open Questions
- Is 1147 already fixed by PR #25? Stale-check before coding.
- Do any TUI P1s share a root cause? Will discover during Phase 2.
