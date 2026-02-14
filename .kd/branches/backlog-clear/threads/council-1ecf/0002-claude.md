---
from: claude
to: king
timestamp: 2026-02-14T19:18:06Z
---

Good. Now I have a clear picture. Here's my recommendation:

---

## Recommended Branch: `ux-polish`

A batch of small, self-contained usability improvements — no new systems, no design work, mostly better CLI output and small ergonomic wins. Here's the grouping:

### Theme 1: "Show me what you did" — Better command output (6 tickets)

These all share one idea: kd commands should tell you what they did, not make you guess.

| Ticket | Title | Effort |
|--------|-------|--------|
| **115f** | `kd tk` commands should echo ticket ID and title in output | Small-medium — touches create/close/start/reopen/move |
| **a24e** | `kd tk start` should print ticket title alongside status change | Duplicate of 115f — merge into it |
| **4884** | `kd tk close` should print ticket title alongside status change | Duplicate of 115f — merge into it |
| **8a92** | `kd done` should show a summary | Small — add ticket count + session cleared message |
| **8cf5** | `kd done` should summarize closed tickets and remind to push | Overlaps 8a92 — merge, one ticket covers both |
| **3ad1** | `kd breakdown` should explain what to do with the printed prompt | Tiny — add a sentence of instructional text |

**Dedup note:** a24e and 4884 are subsets of 115f. 8a92 and 8cf5 are the same ticket written twice. That's 6 tickets collapsing into 3 actual work items.

### Theme 2: CLI ergonomics (4 tickets)

| Ticket | Title | Effort |
|--------|-------|--------|
| **8ff9** | Add `kd tk ls` alias | Tiny — one line |
| **4789** | `kd tk show` should accept multiple IDs or `--all` | Small |
| **2ede** | `kd tk create --dep` to set dependencies at creation time | Small |
| **1c7b** | `kd config show` outputs noisy empty defaults | Small — filter empty values |

### Theme 3: Bug fixes (2 tickets)

| Ticket | Title | Effort |
|--------|-------|--------|
| **083b** | `peasant_start` shadows agent parameter with loop variable | Tiny — rename a variable |
| **2316** | README still advertises removed `kd breakdown --apply` | Tiny — edit docs |

### Theme 4: Scaffold cleanup (1 ticket)

| Ticket | Title | Effort |
|--------|-------|--------|
| **b430** | Remove `learnings.md` from branch scaffold, use `design.md` as shared worklog | Small |

---

## Summary

**12 tickets, collapsing to ~9 actual work items** after deduplication. All are small, well-scoped, and require zero design discussion. The unifying theme is "make kd tell you what it did and stop making you hold state in your head."

## What I'd leave out

- **1147** (peasant --hand bug) — P1 but needs investigation, could be a rabbit hole
- **549b** (council member config) — real feature work, needs design
- **70f6** (council show pagination) — medium-sized feature with UX decisions
- **1e3d** (council auto-commit threads) — touches git workflow, needs thought
- **4994/19b6** (tk log command) — these are duplicates of each other and represent a new command, not a polish
- **d0a2** (peasant review no-diff flag) — needs peasant system understanding
- **c1c7** (tk ready branch vs backlog) — touches ticket prioritization logic
- **9cc9** (config show source indication) — nice but slightly more involved
- All the research/design tickets (520a, 50c7, 3e60, 54e3, etc.)

Want me to help set up the branch and create the tickets from this list?
