---
from: claude
to: king
timestamp: 2026-02-13T12:57:38Z
---

This is a really clean idea. Here's what I think:

**You essentially already have it** — the harness (`run_agent_loop`) is that command. It's the backend-agnostic "execute this ticket" loop. Right now it's just buried as an internal entry point (`kd agent run` / `python -m kingdom.harness`), only invoked by `peasant start`.

The refactor you're describing would be something like:

```
kd work <ticket-id> [--agent claude]
```

This command *is* the harness loop, run in the foreground. That's all it does — pick up a ticket, run the agent loop against it, in whatever directory you're currently in. No worktree creation, no background Popen, no session dance. Just: read ticket, call agent, iterate until done/blocked.

Then `peasant start` becomes a *wrapper* around `kd work` that adds the parallelism concerns:
- Create worktree
- Set up session tracking
- Launch `kd work` as a background subprocess in that worktree
- Track pid, logs, etc.

And `--hand` mode becomes: just run `kd work` in the foreground, in the current directory. Which is exactly what the user does when they're the King working with their preferred agent.

### How it layers:

```
kd work <ticket>              ← core: run harness loop here, now, foreground
                                 (the "execute one ticket" primitive)

kd peasant start <ticket>     ← parallel wrapper: worktree + background + kd work
kd peasant start <ticket> --hand  ← serial: kd work in current dir (foreground)
kd peasant start-ready --hand     ← serial batch: kd work each ready ticket in sequence
```

### What this buys you:

1. **The Hand just runs `kd work`** — it's the natural command for "do this ticket right here." No peasant machinery needed.
2. **Peasant start becomes thinner** — it's just "set up isolation, then `kd work` in the background."
3. **Testability** — `kd work` is a pure execute-in-place command, easy to test without mocking worktrees or processes.
4. **Composability** — a future `kd work --all-ready` that runs tickets serially is trivial. The Hand (or a human!) can just call it.

The harness already doesn't care about worktrees — it takes a `worktree` path and just uses it as `cwd`. So extracting it into `kd work` is mostly just wiring up the CLI entry point and having `peasant start` delegate to it.

Want me to update the design doc with this `kd work` concept as the core primitive?
