---
from: cursor
to: king
timestamp: 2026-02-16T19:50:01Z
---

OpenClaw is a fundamentally different beast than Kingdom, though they share some DNA around "files as memory."

**The Core Difference**
OpenClaw is a **personal daemon**. It's designed to be an always-on "self" that lives on your machine, connects to your chat apps (WhatsApp, Signal, etc.), and maintains a persistent identity. It has a heavy "Gateway" architecture to handle websockets and multiple clients.

Kingdom is a **software factory**. It is a CLI toolkit (`kd`) that orchestrates *other* agents (like me, Claude, or Codex) to ship code. It doesn't want to be your chat buddy; it wants to manage the Design → Breakdown → Ticket → PR lifecycle.

**What's Redundant?**
*   **Context Management:** Both systems solve "how does the agent remember things?" by writing markdown files to disk (`AGENTS.md`, `SOUL.md` in OpenClaw vs `.kd/` state in Kingdom).
*   **Agent Abstractions:** Both have concepts of "tools" and "sessions," though Kingdom delegates the actual execution loop to external CLIs (Claude Code, Cursor Agent), whereas OpenClaw runs its own loop.

**What's Novel in Kingdom?**
*   **Repo-Centric Workflow:** Kingdom's "Repo as Database" approach—storing tickets, designs, and council threads directly in `.kd/`—is unique. OpenClaw treats the *user* as the center of the world; Kingdom treats the *codebase* as the center.
*   **The Council:** Kingdom's multi-model consensus mechanism (querying multiple agents for design review) is a specific workflow innovation not present in OpenClaw's general-purpose runtime.

**What We Should Steal**
I found a few patterns in `docs/third_party/openclaw.md` that we should absolutely adopt:
1.  **"Steering" Semantics:** OpenClaw has a defined protocol for what happens when a user interrupts a running agent (cancel pending tools, inject new instruction). We need this for long-running ticket work.
2.  **Durable Workspace Memory:** OpenClaw injects a `memory/` folder into every session. We should formalize `.kd/runs/<feature>/learnings.md` so I can remember "gotchas" between tickets.
3.  **Idempotency:** OpenClaw requires `idempotencyKey` for side effects. As we build more complex `kd` commands, we should ensure that re-running a command doesn't duplicate tickets or council threads.
