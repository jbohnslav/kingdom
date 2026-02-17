---
from: claude
to: king
timestamp: 2026-02-17T12:29:15Z
---

Looking at the current README to see what's there now and what needs trimming.The King's description of the flow is clearer and more natural than what's in the README now. The current "Core Workflow" section (lines 37-81) repeats what's in "Quick Start" with slightly more detail, and the "Commands" table (lines 104-119) repeats it again. That's three passes over the same information.

Here's what I'd do — replace everything from "Quick Start" through "Commands" with a single walkthrough section that follows the King's narrative:

```md
## Getting Started

```bash
pip install kingdom-cli
```

### 1. Initialize

```bash
kd start              # initialize kd on your current git branch
```

### 2. Configure

Edit `.kd/config.json` to set up your agent CLIs (Claude Code, Codex). They use your existing logins — no extra API keys.

### 3. Design

Use the `kd chat` TUI to talk to the council and iterate on your design doc. Multiple models debate your design decisions in real time.

### 4. Break down

```bash
kd breakdown          # convert design into markdown tickets
```

Review the generated tickets, edit as needed — they're just markdown files.

### 5. Execute

Work tickets in series (tell Claude Code or Codex to work through them) or dispatch peasants to execute in parallel worktrees:

```bash
kd peasant start <id>     # parallel execution in worktrees
kd peasant start --hand   # serial execution in current dir
```

### 6. Finish

```bash
kd done               # archives branch state, verifies all tickets closed
```
```

This keeps the "How It Works" `.kd/` tree diagram (that's genuinely useful for understanding the system) and the Development/License sections at the bottom.

The current version reads like API docs. The King's version reads like a tutorial — which is what a README should be for a tool like this. @codex — anything to add or change before I apply this?
