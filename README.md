# Kingdom

Kingdom (`kd`) is a git-native CLI that helps you plan and ship software by running multi-model AI design councils, turning outcomes into tickets, and executing work through agent workers.

Kingdom is a development workflow layer on top of your existing repo. You define a goal, run a council to get multiple model perspectives on design and tradeoffs, break the result into explicit tickets, and then execute those tickets with worker agents in parallel. The system keeps state in `.kd/` as plain files (tickets, discussions, decisions, archives), so process and decision history stay versioned with your code. It is built for "design first, then implement" teams that want better planning quality and faster execution without replacing git, PRs, or normal engineering practices.

## Install

```bash
pip install kingdom-cli
```

## Quick Start

```bash
# Start a feature (uses current git branch)
kd start

# Write a design doc
kd design

# Get multi-model feedback on your design
kd council ask "How should we handle auth token refresh?"

# Break design into tickets
kd breakdown

# Work tickets
kd ticket list
kd ticket start <id>
kd ticket close <id>

# Finish up — archives branch state
kd done
```

## Core Workflow

### 1. Design

```bash
kd design           # Create design.md template
kd design show      # View design document
kd design approve   # Mark design as approved
```

### 2. Council

Query multiple AI models simultaneously for design decisions:

```bash
kd council ask "How should we implement OAuth refresh tokens?"
kd council status          # Check which members have responded
kd council status -v       # Show log file paths and thread location
```

### 3. Breakdown

```bash
kd breakdown        # Generate tickets from design
```

### 4. Tickets

```bash
kd ticket list              # List tickets for current branch
kd ticket list --all        # List all tickets across branches
kd ticket ready             # Show tickets ready to work on
kd ticket show <id>         # View ticket details
kd ticket start <id>        # Mark in_progress
kd ticket close <id>        # Mark closed
kd ticket create "Title"    # Create new ticket
kd ticket move <id> backlog # Move to backlog
```

### 5. Done

```bash
kd done   # Archive branch folder, clear current
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

## Commands

| Command | Description |
|---------|-------------|
| `kd start [branch]` | Start working on a branch |
| `kd status` | Show current branch and ticket counts |
| `kd done` | Archive current branch |
| `kd design` | Create/view design document |
| `kd design show` | Print design.md |
| `kd design approve` | Mark design approved |
| `kd breakdown` | Generate tickets from design |
| `kd ticket <cmd>` | Ticket management (list, show, create, etc.) |
| `kd council ask` | Query AI council |
| `kd council status` | Check member response status |
| `kd doctor` | Check CLI dependencies |

## Development

```bash
uv sync
source .venv/bin/activate
pytest tests/
```

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
