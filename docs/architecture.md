# Architecture

Kingdom is a CLI tool (`kd`) that manages a ticket-first development workflow. State lives on disk as plain files inside `.kd/`; tickets and worklogs are tracked in git while runtime state is gitignored. No database, no server.

## Module Layout

```
src/kingdom/
├── cli/                # Typer entry point and command modules
├── state.py            # Filesystem layout helpers, path resolution, JSON read/write with flock
├── config.py           # Loads .kd/config.json — agent defs, council composition, prompts
├── agent.py            # Agent configuration, CLI command building per backend (claude_code, codex, cursor)
├── session.py          # Per-agent runtime state (status, resume_id, pid) with advisory locking
├── ticket.py           # Ticket dataclass, YAML frontmatter parsing, read/write/find/move
├── thread.py           # Thread model — sequential message files with frontmatter metadata
├── design.py           # Optional design document template and initialization
├── harness.py          # Autonomous agent loop for peasant execution (prompt → call → parse → repeat)
├── lord_harness.py     # Supervises epic children and peasant execution
├── process.py          # Shared live subprocess streaming and cleanup
├── lifecycle.py        # Normalizes host hook events
├── doctor.py           # Diagnoses repository and host integration state
├── parsing.py          # Shared YAML frontmatter parser used by tickets, threads, and agents
├── council/
│   ├── base.py         # CouncilMember and AgentResponse dataclasses, subprocess runner
│   ├── council.py      # Council orchestration — ThreadPoolExecutor for parallel agent queries
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

Design documents, council consultation, and autonomous
workers are optional layers around this core loop.

### File Storage

Everything is Markdown with YAML frontmatter or plain JSON:

- **Tickets**: `.kd/branches/<branch>/tickets/<id>.md` — frontmatter (status, deps, priority) + body
- **Threads**: `.kd/branches/<branch>/threads/<thread-id>/0001-king.md` — sequential numbered messages
- **Sessions**: `.kd/branches/<branch>/sessions/<agent>.json` — runtime state (gitignored)
- **Execution contexts**: `.kd/runtime/contexts/<context-id>.json` — host identity and current ticket binding (gitignored)
- **Config**: `.kd/config.json` — agent definitions, council members, prompts
- **State**: `.kd/branches/<branch>/state.json` — operational state (gitignored)

Current handlers consume normalized `HostEvent` values; provider payloads are
parsed once at hook ingress. Thread messages carry explicit response status,
which drives council retry, watch output, and TUI rendering.

### Agent Abstraction

`agent.py` defines backend-specific CLI invocation details in `BACKEND_DEFAULTS`. User config from `config.py` (`AgentDef`) is merged at runtime into an `AgentConfig` that command builders consume. This lets the same council/harness code drive the supported Claude Code, Codex, and Cursor backends.

### Concurrency

- **Council queries**: `ThreadPoolExecutor` runs members in parallel, each in its own subprocess.
- **Session state**: `fcntl.flock` advisory locking on JSON files prevents concurrent read-modify-write conflicts between the harness process and CLI commands.
- **Streaming**: peasant and lord subprocesses share concurrent stdout/stderr draining with incremental log flushing.
- **Peasant workers**: Can run in git worktrees (parallel) or serial in the current working directory.

## Extension Points

- **New agent backends**: Add command builders and response parsers in `agent.py`, then extend config validation and runtime checks for the backend.
- **Custom council composition**: Edit `.kd/config.json` to add/remove council members and their models.
- **Prompts**: Override supported council and peasant prompt settings in config.
- **TUI**: The Textual-based chat TUI (`tui/`) provides the interactive `kd council chat` interface.
