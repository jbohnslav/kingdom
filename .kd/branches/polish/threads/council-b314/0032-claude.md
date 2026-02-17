---
from: claude
to: king
timestamp: 2026-02-17T11:55:25Z
---



Let me read the current README first.Good, I can see what we're working with. Here's my take on the description rewrite based on the King's direction:

**One-liner:**
Kingdom (`kd`) is a CLI that lets you design with a multi-agent council, manage work as markdown tickets, and run background RALPH loops with worker peasants — all tracked as plain files in git.

**Opening paragraph + metaphor:**

> The metaphor is the interface: you're the King, a council of AI models debates your design questions, and peasant workers execute tickets in parallel. Gastown minus the polecats.
>
> Kingdom is a development workflow CLI built on top of your existing git repo. You write a design doc, run council sessions where multiple AI models (Claude, GPT, Gemini) hash out tradeoffs, break the result into markdown tickets, and dispatch peasant agents to implement them via RALPH loops in background worktrees. All state — designs, tickets, council threads, archives — lives in `.kd/` as plain files versioned alongside your code. No database, no server, no platform lock-in.

Key changes from what's there now:
- Leads with what it *does* concretely (markdown tickets, multi-agent council, RALPH loops) rather than abstract positioning ("development workflow layer")
- Drops "opinionated" — per the King's note, it's not
- Gets the metaphor in early as a one-liner
- "Gastown minus the polecats" lands right after the metaphor intro
- Names RALPH loops and peasant workers explicitly

Want me to apply this to the README, or does the King want to wordsmith the description further before I touch the file?
