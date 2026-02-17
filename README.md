# Kingdom

Kingdom (`kd`) is a markdown file-based CLI for software development: design with a multi-agent council, track work as markdown tickets, and run background RALPH loops with worker peasants.

The kingdom metaphor is intentional: you are the King, debate your design documents with a council of frontier coding agent CLIs you already use (Claude Code and Codex), break the design into modular markdown tickets, and then peasants execute those tickets in parallel worktrees.

Gastown minus the polecats.

## Why

- **Multi-agent council** — get perspectives from multiple frontier coding models, not just one opinion. Different models catch different things.
- **Ticket-based execution** — breaking work into scoped tickets fights context rot, lets you use cheaper models for already-designed work, or run tickets in parallel.
- **Multi-agent reviews** — reviews across models consistently catch bugs that single-agent reviews miss.
- **Plain markdown files** — tickets, designs, and council threads are all markdown. Your coding agents are already good at finding, reading, and updating markdown.
- **CLI + TUI** — the TUI is for humans; agent CLIs use `kd` directly to ask the council or other agents for opinions.
- **Worklog audit trail** — peasant worklogs capture decisions, bugs encountered, and test results in the ticket markdown, committed to git. You can always see *why* something was done, not just the diff.

## Install

```bash
uv tool install kingdom-cli
```

## Getting Started

1. Initialize the project on your current branch:

```bash
kd start
```

2. Configure council agent CLIs in `.kd/config.json` (check effective config with `kd config show`).

3. Design with the council in the TUI:

```bash
kd chat --new
```

4. Break your design into markdown tickets:

```bash
kd breakdown
```

5. Review and refine tickets:

```bash
kd ticket list
kd ticket show <id>
```

6. Execute tickets:
- Serial: tell Claude Code or Codex to work tickets directly, or run `kd work <id>`.
- Parallel: dispatch peasants in worktrees.

```bash
kd peasant start <id>
kd peasant status
```

7. Close out the session:

```bash
kd done
```

## How It Works

All state lives in `.kd/` as plain Markdown and JSON files, tracked in git alongside your code:

```
.kd/
├── branches/                    # Active branch work
│   └── feature-oauth-refresh/
│       ├── design.md            # Design document
│       ├── breakdown.md         # Ticket breakdown
│       ├── tickets/             # Branch-specific tickets
│       │   ├── a1b2.md
│       │   └── c3d4.md
│       └── threads/             # Council discussion threads
├── backlog/                     # Unassigned tickets
│   └── tickets/
├── archive/                     # Completed branches
└── worktrees/                   # Git worktrees (gitignored)
```

No database. No server. Just files on disk.

## Development

```bash
uv sync
source .venv/bin/activate
pytest tests/
```

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
