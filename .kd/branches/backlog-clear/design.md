# Design: backlog-clear

## Goal

Batch a large group of small, self-contained usability improvements and bug fixes from the backlog into one branch. No new systems, no design work — just CLI polish that makes `kd` noticeably better to use day-to-day.

## Context

The backlog has accumulated ~35 tickets. Many are small UX papercuts noticed during dogfooding: commands that don't tell you what they did, missing aliases, noisy output, shadowed variables, stale docs. Several are duplicates of each other. The council reviewed the full backlog and converged on a clear batch.

## Council Consensus

All three council members (Claude, Cursor, Codex) agreed on a core set of ~12 tickets. Divergences were minor — Codex was most aggressive (20 tickets), Claude most conservative (12 collapsing to 9). The design below follows the consensus core with a few extras where two of three agreed.

## Tickets to Pull

### Theme 1: "Show me what you did" — Better command output

| Ticket | Title | Notes |
|--------|-------|-------|
| 115f | kd tk commands should echo ticket ID and title in output | Core ticket |
| a24e | kd tk start should print ticket title | Dupe of 115f — close as duplicate |
| 4884 | kd tk close should print ticket title | Dupe of 115f — close as duplicate |
| 8a92 | kd done should show a summary | Core ticket |
| 8cf5 | kd done should summarize closed tickets and remind to push | Dupe of 8a92 — merge scope, close as duplicate |
| 3ad1 | kd breakdown should explain what to do with the printed prompt | Tiny |
| 92bd | kd breakdown: don't auto-populate design doc, improve ticket creation guidance | Small |

**Dedup**: 7 tickets → 4 work items (115f, 8a92, 3ad1, 92bd).

### Theme 2: CLI ergonomics

| Ticket | Title | Notes |
|--------|-------|-------|
| 8ff9 | Add `kd tk ls` alias | One-liner |
| 4789 | kd tk show should accept multiple IDs or --all | Small |
| 2ede | kd tk create --dep to set dependencies at creation time | Small |
| 1c7b | kd config show outputs noisy empty defaults | Small — filter empty values |
| 0817 | kd done error should suggest passing branch name | Small — better error message |

### Theme 3: Bug fixes

| Ticket | Title | Notes |
|--------|-------|-------|
| 083b | peasant_start shadows agent parameter with loop variable | Tiny — rename a variable |
| 2316 | README still advertises removed `kd breakdown --apply` | Tiny — edit docs |

### Theme 4: Scaffold cleanup

| Ticket | Title | Notes |
|--------|-------|-------|
| b430 | Remove learnings.md from branch scaffold, use design.md as shared worklog | Small |

## Summary

15 tickets (14 from backlog + 1 new), collapsing to ~11 actual work items after deduplication. All small, well-scoped, zero design needed.

## Non-Goals (leave in backlog)

These were explicitly excluded by the council as too large, needing design, or risky:

- **1147**: Peasant --hand mode bug — P1 but needs investigation, could be a rabbit hole
- **549b**: Council member config — real feature work, needs design
- **70f6**: Council show pagination — medium feature with UX decisions
- **6412**: Council async UX overhaul — large
- **1e3d**: Council auto-commit threads — touches git workflow
- **4994/19b6**: `kd tk log` command — new command, not polish
- **c1c7**: `kd tk ready` branch vs backlog prioritization — touches ticket logic
- **9cc9**: `kd config show` source indication — slightly more involved
- **d0a2**: Peasant review no-diff flag — needs peasant system understanding
- **54e3**: `kd breakdown` should help create tickets — leans toward new feature
- All research/design tickets (520a, 50c7, 3e60, etc.)
- Infrastructure tickets (b5aa, e056, efed)

## Decisions

- **Dedup strategy**: Close a24e, 4884, 8cf5 as duplicates after pulling them in. Work is done under 115f and 8a92.
- **Order**: Bug fixes first (083b, 2316), then output improvements (115f, 8a92, 3ad1), then ergonomics (8ff9, 4789, 2ede, 1c7b, 0817), then scaffold (b430).

## Open Questions

- None — all tickets are straightforward implementation.
