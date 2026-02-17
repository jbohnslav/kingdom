---
from: codex
to: king
timestamp: 2026-02-17T12:30:17Z
---

I’m going to sanity-check the actual CLI commands before we lock the README flow, so we don’t document steps that don’t exist. I’ll verify `kd --help` and current README sections, then propose a tighter rewrite.
I found one mismatch already: `kd chat` is real and should be in the primary flow, and config should be done via `kd config` rather than editing a guessed path. I’m checking subcommand help so we can give exact commands in the README.
I confirmed exact command names and options. I’m pulling the current `README.md` now so I can suggest a single, accurate “happy path” section that matches the CLI today.
Aligned on collapsing it. The README should have one workflow section, not `Quick Start` + `Core Workflow` + `Commands`.

Two fixes before applying:
1. Make `kd chat` the primary design step (King’s requested flow), not `kd council ask`.
2. In config step, say “edit `.kd/config.json`” and optionally “use `kd config show` to view effective config.”

I’d replace the middle with this:

```md
## Getting Started

```bash
pip install kingdom-cli
```

1. Initialize the repo session:

```bash
kd start
```

2. Configure council/agent CLIs in `.kd/config.json` (check effective config with `kd config show`).

3. Design with the council in the TUI:

```bash
kd chat --new
```

4. Break design into tickets:

```bash
kd breakdown
```

5. Review tickets:

```bash
kd ticket list
kd ticket show <id>
```

6. Execute work:
- Serial: work ticket-by-ticket yourself (or run `kd work <id>`).
- Parallel: launch peasants in worktrees:

```bash
kd peasant start <id>
kd peasant status
```

7. Close out the session:

```bash
kd done
```
```

Then keep the `.kd/` tree section, drop the command table. Also fix the top metaphor sentence grammar while you’re in there.
