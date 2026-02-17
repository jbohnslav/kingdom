---
from: claude
to: king
timestamp: 2026-02-17T12:47:26Z
---

Good points — these are the "why should I care" bullets that the current README is missing. Right now it jumps straight from "what is it" to "how to use it" without explaining why any of this matters.

Here's a draft section to go between the intro paragraphs and "Getting Started":

```md
## Why

- **Multi-agent council** — get perspectives from multiple frontier coding models, not just one opinion. Different models catch different things.
- **Ticket-based execution** — breaking work into scoped tickets fights context rot, lets you use cheaper models for already-designed work, or run tickets in parallel.
- **Multi-agent reviews** — reviews across models consistently catch bugs that single-agent reviews miss.
- **Plain markdown files** — tickets, designs, and council threads are all markdown. Your coding agents are already good at finding, reading, and updating markdown.
- **CLI + TUI** — the TUI is for humans; agent CLIs use `kd` directly to ask the council or other agents for opinions.
```

Each bullet maps to one of the King's points. No fluff, no repetition of the intro. @codex — anything to add or reword? King, want me to apply this?
