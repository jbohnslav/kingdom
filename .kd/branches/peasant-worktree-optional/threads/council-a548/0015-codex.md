---
from: codex
to: king
timestamp: 2026-02-13T12:57:54Z
---

I understand the proposal: one unified `kd` command that runs a ticket loop in whatever workspace it’s invoked from, so “Hand on main” and “peasant in worktree” become the same primitive. I’ll read your current design note and map this into the existing CLI/harness model with a minimal change shape.
Yes, that makes sense, and it fits your current architecture well.

You already have the core loop: `kd agent run` (`src/kingdom/cli.py:1639`) and `kingdom.harness.run_agent_loop` (`src/kingdom/harness.py:223`).
So `kd peasant start` can become a thin launcher, and a new unified command can own execution semantics.

Minimal shape:

1. Add `kd ticket execute <ticket> [--agent ...] [--bg] [--hand]`.
2. `--hand` (or main checkout): run loop in current repo root.
3. Worktree context (or non-hand): run loop in current worktree path.
4. `--bg` decides detached peasant-style process; no `--bg` runs foreground Ralph-loop style.
5. Make `kd peasant start` call this internally with `--bg` for backward compatibility.

One practical recommendation: keep async explicit via `--bg` instead of auto-inferred from cwd.
Auto-mode can be surprising; explicit backgrounding is safer and easier to reason about.
