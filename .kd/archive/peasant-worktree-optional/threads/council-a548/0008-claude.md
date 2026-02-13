---
from: claude
to: king
timestamp: 2026-02-12T23:15:35Z
---

This makes total sense. Let me lay out how this fits naturally into the current design.

## How Serial vs Parallel Fits Your Architecture

You're describing two execution modes that map cleanly onto what you already have:

### Mode 1: Parallel (current default) — Peasants in worktrees
```
kd peasant start kin-a1b2 --agent claude
kd peasant start kin-c3d4 --agent claude
# Each in its own worktree, background, autonomous
```

### Mode 2: Serial (the `--hand` flag you're building) — One ticket at a time, main branch
```
kd peasant start kin-a1b2 --hand
# Waits for completion (or runs in foreground-ish)
# Then:
kd peasant start kin-c3d4 --hand
```

The key insight is that these aren't really different *workflows* — they're the same pipeline (design → breakdown → tickets) with a different **execution strategy** at the end. The planning/design/council/breakdown phases are identical. The only fork is at "run the tickets."

### What changes concretely

**What you already have working in the diff:**
- `--hand` flag on `peasant start` that sets `worktree_path = base` instead of creating a worktree — this is exactly right.

**What would make serial mode feel natural:**

1. **`kd peasant start <ticket> --hand` should run in the foreground** (or at least block until done). In parallel mode, peasants are background processes you monitor. In serial/hand mode, the user wants to watch it work. The harness could stream output to the terminal instead of just logging to files.

2. **A convenience command to run tickets serially in sequence**, something like:
   ```
   kd peasant run-all --hand
   ```
   This would grab `kd ticket ready`, run each one serially with `--hand`, auto-review/accept passing ones, and move to the next. Essentially "just do all the work, one ticket at a time, in my current branch." This matches the workflow where you don't want to deal with worktrees at all.

3. **`peasant clean` and `peasant sync` become no-ops in hand mode** — you mentioned this in the design doc and it's the right call. The state tracking just needs to note `"worktree": null` or `"hand": true` so those commands know to skip.

### How this fits the metaphor

The metaphor actually works perfectly:
- **Peasants** = workers dispatched to fields (worktrees) to work in parallel
- **The Hand** = the King's right-hand agent, working *beside* the King in the throne room (current directory), one task at a time

The `--hand` flag is really saying "don't be a peasant in a field — be the Hand working here with me."

### What I'd suggest for the design doc

The design doc you have is solid. The main addition I'd consider is clarifying the **foreground vs background** behavior. Right now `peasant start` always backgrounds the process. For `--hand` mode, the user probably wants:
- Output streamed to terminal (not just to log files)
- Process runs in the foreground (Ctrl+C to stop)
- Or at minimum, automatically tails the log after starting

Want me to update the design doc with these thoughts, or would you rather iterate on the concept more first?
