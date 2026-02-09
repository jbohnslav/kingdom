---
from: claude
to: king
timestamp: 2026-02-09T16:39:38Z
---

Good, I have a thorough picture. Here's the core problem and some approaches:

## The Problem

You're working inside Claude Code (the Hand), and when you run `kd council ask "question"`, it takes 60-120s because it spawns parallel subprocesses for each agent. Claude Code backgrounds long-running commands automatically, so you never see the output inline — it gets captured to a file. You have to then run `kd council show` as a second step.

You want it to feel like a natural conversation: ask a question, see responses appear, without Claude Code hijacking the flow.

## Three Approaches

### 1. **Fire-and-forget + poll display** (what the design doc proposes)

Split into two phases:
- `kd council ask "question"` — dispatches agents in background, returns instantly ("Querying council-abc1...")
- `kd council show --wait` — polls the thread directory, renders each response as it arrives (like a chat room)

**How it works with Claude Code:** The `ask` is instant so CC never backgrounds it. The `show --wait` is a polling loop that prints incrementally — CC sees output arriving and doesn't background it either. You can even skip `show --wait` and come back later with `kd council show`.

**Downside:** Two commands. But `ask` is instant and `show --wait` actively renders, so neither gets swallowed.

### 2. **Single command with streaming output** (best UX)

`kd council ask "question"` dispatches agents in background, then immediately enters a polling loop that prints each response as it lands in the thread directory. Effectively combines approach 1 into one command.

**How it works with Claude Code:** The command starts printing "Waiting for responses..." right away (within 1-2s), then prints each panel as agents finish. CC sees continuous output, so it stays foreground. The command exits after all responses are collected (or on timeout).

```
$ kd council ask "Should we use Redis?"
Council thread: council-a3f2
Querying: claude, codex, cursor...

━━━ codex (34.2s) ━━━
Redis is overkill for this use case...

━━━ claude (47.8s) ━━━  
I'd recommend starting with an in-memory LRU cache...

━━━ cursor (62.1s) ━━━
Consider your deployment topology first...

All responses received.
```

**Key trick:** Start the background agents, then poll `threads/<id>/` for new message files. Print each one as it appears. The subprocess spawning happens in threads, the display loop is the main process. Because output starts flowing quickly, CC treats it as a foreground command.

**Downside:** You're blocked in CC until all responses arrive (60-120s). But you're *watching* them arrive, which feels responsive.

### 3. **Hybrid: async dispatch + show as separate concern**

`kd council ask` always returns instantly (fire-and-forget). Then you teach Claude Code (via CLAUDE.md instructions) to automatically run `kd council show --wait` after `ask`. CC runs both commands sequentially but each one is "well-behaved."

**Downside:** Relies on CC instructions, fragile.

## My Recommendation: Approach 2

The single-command streaming approach is the best fit because:

1. **One command** — no two-step dance
2. **CC-friendly** — output starts within seconds, so it stays foreground
3. **Progressive rendering** — you see each agent's response as it finishes, not all at once
4. **Still async under the hood** — agents run in parallel via ThreadPoolExecutor, responses written to thread as they finish, display loop polls the thread directory
5. **Graceful interruption** — Ctrl+C stops waiting but responses already in the thread are preserved (agents keep running or you kill them)
6. **`kd council show` still works** — if you do interrupt early, you can `show` later to see whatever arrived

The implementation change is small: instead of `council.query()` returning a dict after all agents finish, you'd have it write responses to the thread as each future completes, and the CLI polls the thread directory for new files, rendering each one as it appears.

Want me to plan the implementation for this?
