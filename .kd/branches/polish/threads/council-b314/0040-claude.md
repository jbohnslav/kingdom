---
from: claude
to: king
timestamp: 2026-02-17T12:02:19Z
---

Good call. "Git-native" is vague — it could mean anything. "Markdown file-based" tells you exactly how it works: your tickets, designs, and council threads are markdown files. That's the distinctive thing.

Updated version incorporating that and Codex's tightening:

```md
Kingdom (`kd`) is a markdown file-based CLI for software development: design with a multi-agent council, track work as markdown tickets, and run background RALPH loops with worker peasants.

The kingdom metaphor is intentional: you are the King, the council debates tradeoffs, and peasants execute tickets in parallel worktrees. Gastown minus the polecats.

Kingdom does not replace git or PRs. It stores plans, tickets, council threads, and execution state as plain files in `.kd/`, so your workflow stays transparent, versioned, and portable with your repo.

Start with a goal, run a council session across models (Claude, GPT, Gemini), convert decisions into markdown tickets, and dispatch workers to execute in parallel.
```

@codex — anything else, or should I apply this to the README now?
