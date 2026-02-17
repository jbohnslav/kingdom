---
from: claude
to: king
timestamp: 2026-02-17T12:01:01Z
---

You're right, that's a fair criticism. I read Codex's version and mine and they're saying similar things in slightly different words — we should have been building on each other instead of writing parallel drafts.

Codex's three-paragraph structure is tighter than mine. The opening line is clean, the metaphor sentence lands well, and the third paragraph ("does not replace git or PRs") is a good framing I didn't include. I'd take Codex's version as the base and fold in two things from mine:

1. Name the specific models (Claude, GPT, Gemini) — makes the "multi-agent" claim concrete
2. Mention RALPH loops and worktrees explicitly in the longer section — those are distinctive features worth calling out

Combined version:

```md
Kingdom (`kd`) is a git-native CLI for software teams: design with a multi-agent council, track work as markdown tickets, and run background RALPH loops with worker peasants.

The kingdom metaphor is the UI: you are the King, the council debates tradeoffs across multiple models (Claude, GPT, Gemini), and peasants execute tickets in parallel worktrees. Gastown minus the polecats.

Kingdom does not replace git or PRs. It stores plans, tickets, council threads, and execution state as plain files in `.kd/`, so your process stays transparent, versioned, and portable with your repo.
```

Then the longer section underneath:

```md
Start with a goal, run a council session to hash out design decisions, convert outcomes into markdown tickets, and dispatch peasant workers to implement them via RALPH loops in background worktrees. No server, no database, no platform lock-in.
```

@codex — does that work, or would you change anything? King, want us to apply this?
