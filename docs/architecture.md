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

### Workflow Phases

```
kd start → kd design → kd council ask → kd breakdown → kd ticket work → kd done
```

1. **Start** — `state.py` creates `.kd/branches/<branch>/` directory structure, sets `current` pointer.
2. **Design** — `design.py` generates a `design.md` template. User fills it in, optionally marks approved.
3. **Council** — `council/council.py` fans out a prompt to multiple AI backends in parallel via `ThreadPoolExecutor`. Each `CouncilMember` runs a subprocess (Claude Code, Codex, etc.), streams output to a log file, and writes the response as a message in a thread directory.
4. **Breakdown** — `breakdown.py` produces a prompt to convert the design into tickets. Agent creates ticket files.
5. **Work** — `harness.py` runs an autonomous loop: build prompt from ticket + worklog → call agent CLI → parse response → append to worklog → check stop conditions (done/blocked/failed).
6. **Done** — Archives the branch directory to `.kd/archive/`, clears current pointer.

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
