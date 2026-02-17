---
from: claude
to: king
timestamp: 2026-02-17T01:30:42Z
---



Let me read the current design doc and the existing tickets to write a proper design doc.Good, I can see what's pulled in. Now let me look at the current codebase structure quickly to make sure my design doc references are accurate.Good, I have a full picture. Now let me write the design doc.Ah right — I'm in discussion mode and shouldn't be writing files. Here's the design doc I'd put in `.kd/branches/polish/design.md`:

---

# Design: polish

## Goal

Ship a batch of small, independently-testable UX improvements across the CLI, chat TUI, and council output. Every ticket should be completable in under half a day. No new subsystems, no permissions infrastructure — just make what exists feel better.

## Context

After several rounds of feature work (chat TUI, council streaming, peasants, config system), the rough edges are piling up: inconsistent output formatting, missing convenience commands, chat actions that should exist but don't, and visual polish that would make the tool more pleasant to use daily.

## Scope: In This Branch (~32 tickets)

### A. Ticket CLI Polish (13 tickets)

| # | Ticket | Description |
|---|--------|-------------|
| 1 | 4994/19b6 | **`kd tk log`** — core command (deduplicate these two) |
| 2 | 3c59 | **`kd tk current`** — show in-progress ticket |
| 3 | 9fd5 | **`kd tk list`**: group or filter by status |
| 4 | 3159/3269 | **`kd tk list`**: summary counts / progress bar (deduplicate) |
| 5 | 021e | **`kd tk list`**: dependency arrows or indentation |
| 6 | f279 | **`kd tk show`**: display dep status inline |
| 7 | 5391 | **`kd tk close`**: optional reason message |
| 8 | b924 | **`kd tk close`**: show newly unblocked tickets |
| 9 | 2def | **`kd tk create`**: print created file path |
| 10 | db2e | **`kd tk create --backlog`**: confirm where ticket landed |
| 11 | NEW | **`kd tk list`**: Rich table formatting |
| 12 | NEW | **`kd tk show`**: structured Rich panel layout |
| 13 | NEW | **`kd tk move`**: clarify success message |

### B. Chat TUI Polish (9 tickets)

| # | Ticket | Description |
|---|--------|-------------|
| 14 | efaf | **Copy-to-clipboard** action on messages |
| 15 | NEW | **Reply button** — quote + @mention sender |
| 16 | ab5d | **@mentions**: tab-complete and colored rendering |
| 17 | 9725 | **Brand-aware default member colors** |
| 18 | NEW | **Thinking duration**: format as `1m 23s` over 60s |
| 19 | NEW | **Error panel**: show context and retry hint |
| 20 | NEW | **Slash command discoverability** in UI |
| 21 | NEW | **Auto-scroll**: don't snap while user reads history |
| 22 | NEW | **Expand color palette** beyond 6 fallbacks |

### C. CLI Output Consistency (4 tickets)

| # | Ticket | Description |
|---|--------|-------------|
| 23 | NEW | **Standardize error output** with Rich styling |
| 24 | NEW | **Empty-state messages** with next-step guidance |
| 25 | NEW | **Ctrl+C messaging** — clean interruption |
| 26 | NEW | **`kd done` structured summary** panel |

### D. Council Output Polish (3 tickets)

| # | Ticket | Description |
|---|--------|-------------|
| 27 | c247 | **Thread auto-pickup** improvement |
| 28 | NEW | **Council status symbol legend** |
| 29 | 1e3d | **Auto-commit thread files** after all respond |

### E. Housekeeping (3 tickets)

| # | Ticket | Description |
|---|--------|-------------|
| 30 | ca69 | **Bug**: `kd tk dep` overwrites instead of appending |
| 31 | 12c6 | **Code hygiene**: move `is_error_response()` to thread.py |
| 32 | c937 | **Remove Cursor and Gemini** as council members |

## Backlog (Not This Branch)

- Council permissions / writable mode (b057)
- `tk log` advanced filters (--since, --actor, --type, --follow)
- Mentions fuzzy matching, recency ranking, Shift+Tab
- Terminal capability detection (NO_COLOR, TERM=dumb, truecolor)
- Colorblind-safe palette
- Accessibility (screen reader, reduce-motion)
- Chat group modes (7afc), LLM-to-LLM mentions (7a1d), Phase 2 (3e60)
- `tk delete` (1fa5), `tk close --duplicate-of` (f172), `tk undep` (03b1)
- Auto-detect session (efed), config show source (9cc9), --verbose (d04c)
- Config schema validation (e880), council review shortcut (1c4b)
- `tk ready` prioritization (c1c7), `tk list --backlog -p` filter (d739)

## Decisions

- **Council permissions**: Drop Gemini, rely on instruction-following from Opus/Codex. "Don't act unless I say 'open the ticket'." Backlog the formal permissions system.
- **Dedup**: Close 19b6 as dup of 4994 (tk log). Close 3269 as dup of 3159 (summary counts).
- **Ordering**: Start with daily drivers — tk list, tk show, tk close, chat copy/reply.
- **Output standard**: All new output uses Rich. No new `typer.echo()` or `print()`.

## Open Questions

- Should `kd tk log` be worklog-append (journal) or event-log (automatic history)? Leaning append — git history already covers events.
- Chat reply: blockquote of original, or just @mention with ref? Blockquote is more useful but takes space.

---

That's the full design doc. Want me to proceed, or should we discuss the open questions and prioritization first?
