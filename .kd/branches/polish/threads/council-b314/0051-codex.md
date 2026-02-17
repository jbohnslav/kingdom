---
from: codex
to: king
timestamp: 2026-02-17T12:47:45Z
---

I’d ship this, right above `Getting Started`:

```md
## Why Kingdom

- **Best-of-models design**: the council pulls in multiple frontier coding agent CLIs you already use (Claude Code, Codex), so decisions are based on debate, not a single model’s blind spots.
- **Scoped markdown tickets**: breaking work into small, designed tickets reduces context rot, lets you hand execution to cheaper models, and makes parallel work practical.
- **Stronger reviews**: multi-agent review catches classes of bugs and regressions that single-agent review routinely misses.
- **Markdown-native workflow**: plans, tickets, and discussions are plain markdown files, so both humans and coding agents can find, read, diff, and update them easily.
- **Human TUI, agent CLI**: humans use `kd chat` for fast iteration; agent CLIs can call `kd` directly to ask the council or other agents for additional opinions.
```

This matches your positioning and avoids redundancy with the usage steps.
