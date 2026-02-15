---
from: claude
to: king
timestamp: 2026-02-15T22:53:50Z
---



Let me pull up the breakdown and all the tickets.The breakdown.md is still the template — the real content is in the tickets. Let me read each one.Now let me check the dependency graph to verify correctness.Let me reconstruct the dependency graph from what I've read.Good. Let me verify the config schema ticket doesn't have any dependents that need it earlier in Phase 1.Here's my review of the ticket breakdown.

## Dependency Graph

```
8ea4 (config schema)          b71d (TUI skeleton)            f9d2 (Popen handle)
    │                        ┌───┴───┐                           │
    │                       bb51    fe84                          │
    │                   (widgets) (polling)                       │
    │                        └───┬───┘                           │
    │                          7ddd (ChatApp layout)             │
    │                        ┌───┴───────────────────┐           │
    │                       7656                    16e1 ←───────┘
    │                   (history display)     (input/dispatch)
    │                        │             ┌────┴────┐
    │                       213e         4a91      d869
    │                   (format_history) (streaming) (escape)
    │                        └────┬────┘
    │                           3b76 (auto-turn scheduler)
    │
   8461 (configurable preamble)
```

## What's Right

**The layering is correct.** Foundation tickets (b71d, 8ea4, f9d2) have no deps. UI building blocks (bb51, fe84) depend on the skeleton. Assembly (7ddd) depends on the parts it composes. Feature tickets (16e1, 4a91) depend on the assembled layout. Phase 2 tickets (3b76, 213e, d869) depend on Phase 1 completion. Phase 3 (8461) depends only on the config ticket. Good topological ordering.

**Scope per ticket is reasonable.** Each ticket is a coherent unit of work with clear acceptance criteria. None are so large they'll take multiple days, none are so small they're just busywork.

## Issues

### 1. `8ea4` (config schema) is disconnected from the TUI chain — should it be?

8ea4 adds `auto_rounds`, `mode`, and `preamble` to `CouncilConfig`. But the only tickets that *consume* these values are 3b76 (auto-turn scheduler, reads `auto_rounds` and `mode`) and 8461 (configurable preamble, reads `preamble`). Neither depends on 8ea4.

**3b76 should depend on 8ea4** — the auto-turn scheduler reads `council.auto_rounds` and `council.mode` from config. Without 8ea4, those fields don't exist on `CouncilConfig`. Add the dependency.

8461 already depends on 8ea4, so that's fine.

### 2. `7656` (thread history display) is P2 but it's needed for Phase 1

The design says Phase 1 includes: "When resuming a thread, show full history (all messages in sequence order)." That's exactly what 7656 does. But it's marked P2, while the Phase 1 tickets are P1. If you open an existing thread in the TUI (via `kd chat` or `kd chat <thread-id>`) and it doesn't show history, the TUI is broken for the most basic resume case.

**Recommend: promote 7656 to P1.** It's a core Phase 1 feature.

### 3. `16e1` (user input) is overloaded

This ticket covers:
- Enter/Shift+Enter keybindings
- Input area auto-growth
- @member addressing and parsing
- King message writing to thread files
- Query dispatch via `asyncio.to_thread()`
- /mute, /unmute, /help, /quit slash commands
- Error panel rendering for agent failures

That's at least three distinct concerns: (a) input handling and keybindings, (b) query dispatch and thread message writing, (c) slash commands. Implementing all of these in one pass means the ticket can't be tested incrementally — you can't verify slash commands work until dispatch works, and dispatch requires input handling.

**Recommend: split into two tickets.**
- **16e1a**: Input handling + query dispatch — Enter sends, Shift+Enter newlines, write king message, launch `member.query()` via `asyncio.to_thread()`, @member addressing. This is the critical path.
- **16e1b**: Slash commands — /mute, /unmute, /help, /quit. Depends on 16e1a. These are self-contained and independently testable.

### 4. `4a91` (streaming display) overlaps with `7656` (history display) on external stream file detection

Both tickets mention detecting in-flight `.stream-{member}.jsonl` files from external processes. 4a91 says "In-flight external stream files shown as read-only StreamingPanels (no duplicate queries launched)." 7656 says "In-flight `.stream-{member}.jsonl` files detected and shown as read-only StreamingPanels."

**Recommend: keep this in 7656 only** (on-open detection), and have 4a91 focus on the steady-state polling lifecycle. 7656 handles "what state are we in when the TUI opens," 4a91 handles "what transitions happen while the TUI is running." Right now they both claim the same feature.

### 5. `213e` (format_thread_history) depends on `7656` — why?

213e is a pure function: read thread messages, format them as a multi-party prompt string. It has no dependency on the TUI display at all. Its dependency on 7656 (thread history display on open) doesn't make sense — formatting a prompt string doesn't require the TUI to be able to render history.

**Recommend: remove the dep on 7656.** 213e should depend on nothing (or at most b71d for the module location, if it lives in `tui/`). Actually, `format_thread_history()` probably belongs in `kingdom/thread.py` or `kingdom/council/`, not in `tui/` — it's used by the auto-turn scheduler which is orchestration logic, not UI. If it lives outside `tui/`, it has zero TUI dependencies.

This also unblocks 3b76 (auto-turn scheduler) from the long dependency chain through the TUI display tickets.

### 6. No ticket for `council.mode: "sequential"` behavior in Phase 1

The design says Phase 1 is broadcast only, Phase 2 adds `mode: "sequential"`. Ticket 3b76 (auto-turn scheduler, P2) mentions `council.mode: "sequential" skips the initial parallel broadcast` in its acceptance criteria. This is correct — but 16e1 (user input, P1) launches parallel queries for broadcast and doesn't mention the sequential path at all.

This is fine as-is (P1 always broadcasts, P2 adds sequential), but worth confirming that's the intent. If someone sets `council.mode: "sequential"` in config during Phase 1, 16e1 would ignore it and broadcast anyway. Not a bug, just a gap to be aware of.

### 7. No ticket for `kd chat` thread selection UX

The design says: "If no current thread and no `--new`, show recent threads and offer to create one." Ticket b71d covers the CLI args (`--new`, `<thread-id>`, default current thread) and "if none, prints helpful message." But "show recent threads and offer to create one" is more than a helpful message — it's a mini thread picker.

This is a small enough feature that it could stay in b71d, but the acceptance criteria should be sharpened: is it just a list printed to stdout with instructions, or is it a Textual selection screen? I'd recommend the simple version (print list, tell user to run `kd chat <id>` or `kd chat --new`) and punt the fancy picker to a backlog ticket.

### 8. Missing: a "smoke test / integration test" ticket

There's no ticket for end-to-end verification that the TUI actually works as a whole. Individual tickets test their components, but the full lifecycle (open TUI → type message → see waiting → see streaming → see finalized response → type another message) only gets verified in 4a91's manual test acceptance criterion.

**Recommend: add a P1 ticket** that depends on 4a91 and 7656, scoped to: "Manual smoke test of the full Phase 1 TUI lifecycle. Document any bugs found, file as new tickets." This forces a real dogfooding pass before Phase 2 work begins.

## Summary

The breakdown is well-structured. The main action items:

1. **Add dependency**: 3b76 → 8ea4 (scheduler needs config keys)
2. **Promote**: 7656 from P2 to P1 (history display is core Phase 1)
3. **Split**: 16e1 into input/dispatch + slash commands
4. **Deduplicate**: external stream file detection (keep in 7656, remove from 4a91)
5. **Fix dependency**: 213e should not depend on 7656 — it's a pure function
6. **Add ticket**: Phase 1 end-to-end smoke test
7. **Clarify**: b71d thread selection UX scope (simple list vs. Textual picker)
