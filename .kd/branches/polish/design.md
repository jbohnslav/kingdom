# Design: polish

## Goal

Ship a batch of small, independently-testable UX improvements across the CLI, chat TUI, and council output. Every ticket should be completable in under half a day. No new subsystems, no permissions infrastructure — just make what exists feel better.

## Context

After several rounds of feature work (chat TUI, council streaming, peasants, config system), the rough edges are piling up: inconsistent output formatting, missing convenience commands, chat actions that should exist but don't, and visual polish that would make the tool more pleasant to use daily.

## Non-Goals

- New features (peasant redesign, council permissions/writable mode, chat Phase 2, group chat modes)
- Terminal capability detection (NO_COLOR, truecolor, colorblind palettes)
- Accessibility (screen reader, reduce-motion)
- Advanced tk log filters (--since, --actor, --type, --follow)

## Decisions

- `kd tk log` is a **worklog-append journal** (human writes entries), not an automatic event log. Git history already covers events.
- **Council permissions**: Drop Gemini and Cursor. Rely on instruction-following from Opus and Codex — "don't act unless I say 'open the ticket'." Backlog the formal permissions system.
- **Dedup**: 19b6 closed as dup of 4994 (tk log). 3269 closed as dup of 3159 (summary counts).
- **Output standard**: All new output uses Rich. No new `typer.echo()` or `print()`.
- **Ordering**: Start with daily drivers — tk list, tk show, tk close, chat copy/reply.

---

## Scope: In This Branch (~36 tickets)

### A. Ticket CLI Polish (14 tickets)

| Ticket | Description |
|--------|-------------|
| 4994 | `kd tk log` — append worklog journal entries |
| 3c59 | `kd tk current` — show in-progress ticket |
| 9fd5 | `kd tk list`: filter by status |
| 3159 | `kd tk list`: summary counts / progress bar |
| 021e | `kd tk list`: dependency arrows or indentation |
| a01d | `kd tk list`: Rich table formatting |
| f279 | `kd tk show`: dep status inline |
| ed73 | `kd tk show`: structured Rich panel layout |
| 5391 | `kd tk close`: optional reason message |
| b924 | `kd tk close`: show newly unblocked tickets |
| 2def | `kd tk create`: print file path |
| db2e | `kd tk create --backlog`: confirm where ticket landed |
| 21c1 | `kd tk move`: human-readable location in success message |
| ca69 | Bug: `kd tk dep` overwrites deps instead of appending |

### B. Chat TUI Polish (11 tickets)

| Ticket | Description |
|--------|-------------|
| efaf | Copy-to-clipboard action on messages |
| 3f8c | Reply button — quote + @mention sender |
| ab5d | @mentions tab-complete and colored rendering |
| 9725 | Brand-aware default member colors |
| 55cf | Thinking duration formatted as `1m 23s` |
| 4e8c | Error panel with context and retry hint |
| b1dd | Slash command discoverability |
| 603d | Auto-scroll — don't snap while reading history |
| 88e3 | Expand color palette beyond 6 fallbacks |
| 03ea | Thinking visibility toggle hotkey |
| e0eb | Inject branch context + tk list into chat system prompt |

### C. CLI Output Consistency (7 tickets)

| Ticket | Description |
|--------|-------------|
| 968b | Standardize error output styling (Rich everywhere) |
| 3106 | Empty-state messages with next-step guidance |
| c790 | Replace raw `print()` with `console.print()` |
| ce6b | Standardize success message format |
| ec29 | `kd done` structured summary panel |
| d6df | Worklog timestamps include date context |
| 8dea | Chat Textual polish pass (research best-in-class) |

### D. Council Output Polish (3 tickets)

| Ticket | Description |
|--------|-------------|
| c247 | Thread auto-pickup improvement |
| b42a | Council status symbol legend |
| 9e92 | `kd council show --last N` for long threads |

### E. Housekeeping (2 tickets)

| Ticket | Description |
|--------|-------------|
| c937 | Remove Cursor and Gemini 3 as council members |
| 12c6 | Move `is_error_response()` to thread.py |
