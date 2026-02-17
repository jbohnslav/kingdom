---
from: codex
to: king
timestamp: 2026-02-17T12:01:16Z
---

Yes, this is close. I’d use Claude’s merged version with one tightening pass so it reads less like marketing and more like product truth.

```md
Kingdom (`kd`) is a git-native CLI for software development: design with a multi-agent council, track work as markdown tickets, and run background RALPH loops with worker peasants.

The kingdom metaphor is intentional: you are the King, the council debates tradeoffs, and peasants execute tickets in parallel worktrees. Gastown minus the polecats.

Kingdom does not replace git or PRs. It stores plans, tickets, council threads, and execution state as plain files in `.kd/`, so your workflow stays transparent, versioned, and portable with your repo.

Start with a goal, run a council session across models (Claude, GPT, Gemini), convert decisions into markdown tickets, and dispatch workers to execute in parallel.
```

If you want, I’ll patch this directly into `README.md` and then normalize the next few sections to match the same voice.
