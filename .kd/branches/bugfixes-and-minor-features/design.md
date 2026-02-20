# Design: bugfixes-and-minor-features

## Goal
Stabilize kd by fixing all P1 bugs and shipping small P2 improvements — no new major features, just making what exists work better.

## Context
The backlog has accumulated several crash-level bugs in the Chat TUI (color attribute errors in long sessions, crashes on concurrent sends, broken auto-scroll) and peasant workflow (--hand mode exits immediately). There are also a handful of small CLI quality-of-life gaps (no `tk delete`, no `tk undep`, no priority filtering on backlog list, etc.). This branch batches them all into one sweep.

## Requirements
- Fix all P1 bugs: Chat TUI color crash, auto-scroll, concurrent send crash, peasant --hand, pre-existing test failure
- Fix P2 bugs: click-inserts-commas, MountError on ErrorPanel, @all broadcast regression
- Add minor CLI features: `tk undep`, `tk delete`, `tk close --duplicate-of`, `tk ready` branch/backlog separation, backlog priority filter, `config show` source indication, peasant sync progress, peasant review no-diff warning, NO_COLOR/TERM=dumb support
- Full test suite green after each ticket

## Non-Goals
- Chat TUI Phase 2 or Phase 3 features
- New agent backends (Gemini, OpenCode)
- Integration test infrastructure
- Public repo / release workflow changes

## Decisions
- Work P1 bugs first, then P2 bugs, then minor features
- Each fix is one ticket, committed independently
- No design council needed — these are all well-scoped fixes

## Open Questions
- None — all tickets are self-contained
