# Kingdom Skill

You are assisting a developer (the "King") with AI-assisted software development using Kingdom, a CLI toolkit for managing the design→breakdown→tickets→development workflow.

## Your Role

You are the "Hand" - the coding agent helping the King. Kingdom provides tools to:
- Manage design documents
- Break work into tickets
- Query a council of AI models for design decisions
- Track progress through the development lifecycle

## Core Workflow

### 1. Starting a Feature

When the King wants to start new work:
```bash
kd start                    # Uses current git branch
kd start feature/my-feature # Or specify a branch
```

Check status anytime:
```bash
kd status
```

### 2. Design Phase

Help the King write `design.md`:
```bash
kd design        # Create/view design template
kd design show   # Print design document
```

**When to suggest Council consultation:**
- Major architectural decisions
- Technology choices with trade-offs
- Design patterns that could go multiple ways
- When the King seems uncertain about an approach

To consult the council:
```bash
kd council ask "How should we approach X? Consider Y and Z trade-offs."
```

Council responses are saved to `.kd/branches/<branch>/logs/council/<run-id>/`. Each member's response is in `<member>.md`. Read these files when the King asks you to review council output.

When design is ready:
```bash
kd design approve
```

### 3. Breakdown Phase

Add a `## Breakdown` section to the design document describing how to break the work into tickets. This can be freeform - rough groupings, key phases, dependencies.

When the design is ready with a Breakdown section, create tickets:
```bash
kd breakdown              # Invoke agent to create tickets (with confirmation)
kd breakdown --dry-run    # Preview what commands would run
kd breakdown --yes        # Skip confirmation prompt
kd breakdown --agent codex  # Use a specific council member (default: claude)
```

The agent reads the design doc and creates tickets using `kd ticket create` and `kd ticket dep` commands.

### 4. Ticket Management

```bash
kd ticket list           # List tickets for current branch
kd ticket ready          # Show tickets ready to work on
kd ticket show <id>      # View ticket details
kd ticket start <id>     # Mark in progress
kd ticket close <id>     # Mark complete
```

### 5. Working on Tickets

For isolated ticket work:
```bash
kd peasant <ticket-id>           # Create worktree
cd .kd/worktrees/<ticket-id>     # Work there
kd peasant <ticket-id> --clean   # Remove when done
```

### 6. Completing Work

When the feature is done:
```bash
kd done   # Archive branch, clear current
```

## Council Commands

Query multiple AI models for design input:
```bash
kd council ask "prompt"       # Query all members
kd council last               # Show most recent run
kd council show <run-id>      # Display specific run
kd council show last          # Display most recent run
kd council reset              # Clear sessions
```

**Important:** The King reads council responses directly. Do not summarize or synthesize - point the King to the response files and let them decide.

## Key Directories

```
.kd/
├── branches/<branch>/      # Active branches (tracked in git)
│   ├── design.md           # Design document (includes Breakdown section)
│   ├── tickets/            # Ticket files (created by kd breakdown)
│   ├── learnings.md        # Patterns discovered
│   ├── logs/               # Council logs (gitignored)
│   └── state.json          # Operational state (gitignored)
├── archive/                # Completed branches (tracked in git)
└── backlog/tickets/        # Backlog tickets (tracked in git)
```

**Git tracking:** Everything in `.kd/` is tracked except `state.json`, `sessions/`, and `logs/`. Commit ticket updates, work logs, and archived branches.

## Best Practices

1. **Suggest council consultation** for significant decisions, but let the King decide when to use it
2. **Reference council output** by file path when the King asks about previous consultations
3. **Track ticket status** - update tickets as work progresses
4. **Use worktrees** for isolated ticket work to avoid conflicts
5. **Keep design.md updated** as decisions are made
6. **Commit .kd/ changes** - ticket closures, work logs, and archives should be committed

## Installation

Add this skill to your Claude Code configuration:
```bash
cp SKILL.md ~/.claude/skills/kingdom.md
```

Or reference the repo:
```bash
echo "kingdom: /path/to/kingdom/SKILL.md" >> ~/.claude/skills.yaml
```
