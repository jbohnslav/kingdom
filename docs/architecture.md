# Architecture

Kingdom is a CLI tool (`kd`) that manages a design-first development workflow. All state lives on disk as plain files inside `.kd/`, tracked in git alongside your code. No database, no server.

## Module Layout

```
src/kingdom/
├── cli.py              # Typer CLI — all commands and subcommands
├── state.py            # Filesystem layout helpers, path resolution, JSON read/write with flock
├── config.py           # Loads .kd/config.json — agent defs, council composition, prompts
├── agent.py            # Agent configuration, CLI command building per backend (claude_code, codex, cursor)
├── session.py          # Per-agent runtime state (status, resume_id, pid) with advisory locking
├── ticket.py           # Ticket dataclass, YAML frontmatter parsing, read/write/find/move
├── thread.py           # Thread model — sequential message files with frontmatter metadata
├── design.py           # Design phase helpers — template generation, response parsing
├── breakdown.py        # Breakdown phase — generates tickets from design doc
├── harness.py          # Autonomous agent loop for peasant execution (prompt → call → parse → repeat)
├── synthesis.py        # Synthesis prompt builder for combining multi-model council responses
├── parsing.py          # Shared YAML frontmatter parser used by tickets, threads, and agents
├── council/
│   ├── base.py         # CouncilMember and AgentResponse dataclasses, subprocess runner
│   ├── council.py      # Council orchestration — ThreadPoolExecutor for parallel agent queries
│   ├── bundle.py       # Run bundle creation — snapshots a council run with metadata
│   └── worker.py       # Standalone council worker entry point
└── tui/
    ├── app.py          # Textual TUI app for interactive council chat
    ├── widgets.py      # Custom widgets (message bubbles, markdown rendering)
    ├── poll.py         # Background poller for new thread messages
    └── clipboard.py    # Cross-platform clipboard support
```

## Data Flow

### Core Workflow

```
kd start → kd tk create/start → work/log/test → kd tk close → kd status --check
```

1. **Start** — `state.py` initializes, resumes, or selects the branch workspace and repository fallback.
2. **Tickets** — ticket Markdown records executable work, relationships, acceptance criteria, and durable Worklogs.
3. **Work** — a direct agent or optional peasant implements and verifies one ticket at a time.
4. **Close** — `kd tk close` records a terminal resolution and clears active bindings for that ticket.
5. **Readiness** — `kd status --check` derives workspace readiness from ticket state without changing it.

Design documents, council consultation, breakdown generation, and autonomous
workers are optional layers around this core loop.

### File Storage

Everything is Markdown with YAML frontmatter or plain JSON:

- **Tickets**: `.kd/branches/<branch>/tickets/<id>.md` — frontmatter (status, deps, priority) + body
- **Threads**: `.kd/branches/<branch>/threads/<thread-id>/0001-king.md` — sequential numbered messages
- **Sessions**: `.kd/branches/<branch>/sessions/<agent>.json` — runtime state (gitignored)
- **Config**: `.kd/config.json` — agent definitions, council members, prompts
- **State**: `.kd/branches/<branch>/state.json` — operational state (gitignored)

### Agent Abstraction

`agent.py` defines backend-specific CLI invocation details in `BACKEND_DEFAULTS`. User config from `config.py` (`AgentDef`) is merged at runtime into an `AgentConfig` that command builders consume. This lets the same council/harness code drive Claude Code, Codex, Cursor, or any CLI-based agent.

### Concurrency

- **Council queries**: `ThreadPoolExecutor` runs members in parallel, each in its own subprocess.
- **Session state**: `fcntl.flock` advisory locking on JSON files prevents concurrent read-modify-write conflicts between the harness process and CLI commands.
- **Peasant workers**: Can run in git worktrees (parallel) or serial in the current working directory.

## Extension Points

- **New agent backends**: Add entries to `BACKEND_DEFAULTS` in `agent.py` and define an `AgentDef` in config.
- **Custom council composition**: Edit `.kd/config.json` to add/remove council members and their models.
- **Phase prompts**: Override default prompts for design, breakdown, and work phases in config.
- **TUI**: The Textual-based chat TUI (`tui/`) provides the interactive `kd chat` interface.
