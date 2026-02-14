# Kingdom

A CLI toolkit for AI-assisted software development. Kingdom helps you manage the design→breakdown→tickets→development workflow alongside your coding agent (Claude Code, Cursor, etc.).

## Quick Start

```bash
# Install
pip install -e .

# Start a feature (uses current git branch)
kd start

# Or start with a specific branch name
kd start feature/oauth-refresh

# Check status
kd status
```

## Core Workflow

### 1. Design Phase

```bash
kd design           # Create design.md template
kd design show      # View design document
kd design approve   # Mark design as approved
```

### 2. Breakdown Phase

```bash
kd breakdown        # Print agent prompt to create tickets from design
```

### 3. Ticket Management

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

### 4. Multi-Model Council

Query multiple AI models simultaneously for design decisions:

```bash
kd council ask "How should we implement OAuth refresh tokens?"
kd council status          # Check which members have responded
kd council status -v       # Show log file paths and thread location
```

### 5. Complete Feature

```bash
kd done   # Archive branch folder, clear current
```

## Directory Structure

```
.kd/
├── branches/                    # Active branch work
│   └── feature-oauth-refresh/   # Normalized from feature/oauth-refresh
│       ├── design.md            # Design document (tracked)
│       ├── breakdown.md         # Ticket breakdown (tracked)
│       ├── tickets/             # Branch-specific tickets (tracked)
│       │   ├── kin-a1b2.md
│       │   └── kin-c3d4.md
│       └── state.json           # Operational state (ignored)
├── backlog/                     # Unassigned tickets
│   └── tickets/
├── archive/                     # Completed branches
├── worktrees/                   # Git worktrees (ignored)
└── current                      # Pointer to active branch (ignored)
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `kd start [branch]` | Start working on a branch |
| `kd status` | Show current branch and ticket counts |
| `kd done` | Archive current branch |
| `kd design` | Create/view design document |
| `kd design show` | Print design.md |
| `kd design approve` | Mark design approved |
| `kd breakdown` | Print agent prompt to create tickets from design |
| `kd ticket <cmd>` | Ticket management (list, show, create, etc.) |
| `kd council ask` | Query AI council |
| `kd council status` | Check member response status |
| `kd doctor` | Check CLI dependencies |

## Development

```bash
# Setup
uv sync
source .venv/bin/activate

# Optional: expose this repo's Kingdom skill to your agent tool
ln -s "$(pwd)/skills/kingdom" ~/.codex/skills/private/kingdom
# or
ln -s "$(pwd)/skills/kingdom" ~/.claude/skills/kingdom

# Run tests
pytest tests/

# Smoke test
./scripts/smoke.sh
```

## License

MIT
