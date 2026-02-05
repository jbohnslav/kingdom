# Analysis: Beads (bd)

## Overview

**Beads** is a distributed, git-backed issue tracker designed for AI agents. It stores issues as JSONL in a `.beads/` directory (git-tracked) with SQLite as a local query cache. A background daemon handles auto-sync between SQLite and JSONL, ensuring consistency across git operations.

**Core purpose**: Provide persistent, structured memory for coding agents. Replace messy markdown plans with a dependency-aware graph that survives context window limits.

**What beads solves**: The "long-horizon task problem." Agents lose context across sessions. Beads provides a persistent graph of issues with dependencies, allowing agents to resume work, understand what's blocked, and track progress across multiple sessions.

## Core Architecture

### Three-Layer Data Model

```
CLI Layer (Cobra commands)
    ↓ (sync every 5s via FlushManager)
SQLite Database (.beads/beads.db)
    ↓ (auto-sync with 30s debounce)
JSONL File (.beads/issues.jsonl)  ← git-tracked
    ↓ (git push/pull)
Remote Repository
```

**Write path**: Command → SQLite → JSONL (debounced) → git commit
**Read path**: Git pull → auto-import JSONL → SQLite → queries

### Key Files

```
.beads/
├── beads.db       # SQLite cache (gitignored)
├── issues.jsonl   # Git-tracked issue store (one JSON object per line)
├── config.yaml    # Project configuration
└── bd.sock        # Daemon socket (if running)
```

### Issue Model

Issues have rich fields beyond basic tracking:

- **Core**: ID (hash-based), Title, Description, Status, Priority
- **Workflow**: Design, AcceptanceCriteria, Notes
- **Relationships**: Dependencies (blocks/related/parent-child), Labels, Comments
- **Agent features**: AgentState, RoleBead, HookBead, Molecules (swarm/patrol/work)
- **Events**: Full audit trail of all changes

### Hash-Based IDs

IDs like `bd-a3f8` are derived from SHA256 hashes, preventing merge conflicts in multi-agent/multi-branch workflows. Progressive scaling grows IDs from 4 to 6 characters as the database grows.

## Kingdom's `ticket` Script

Kingdom currently uses a ~1500 line bash script that stores markdown files with YAML frontmatter:

```
.tickets/
├── kin-a1b2.md
├── kin-c3d4.md
└── ...
```

Each file has:
```yaml
---
id: kin-a1b2
status: open
deps: [kin-x1y2]
links: []
created: 2025-01-15T10:30:00Z
type: task
priority: 2
assignee: jrb
---
# Ticket Title

Description...
```

### Feature Comparison

| Feature | Beads | Kingdom `ticket` |
|---------|-------|------------------|
| Storage | JSONL + SQLite | Markdown files |
| Queries | Fast SQLite | awk parsing |
| Git sync | Auto (daemon) | Manual |
| Dependencies | Typed (blocks/related/parent) | Single type (deps) |
| Agent-oriented fields | Yes (molecules, hooks, wisps) | No |
| Daemon | Yes | No |
| JSON output | `--json` flag | `query` command |
| Language | Go (~70k lines) | Bash (~1500 lines) |
| Install | brew/npm/go | Just copy the script |

## Patterns Worth Adopting

### 1. The `ready` Command Pattern

**What beads does well**: `bd ready` shows issues with no open blockers—the natural "what should I work on next?" query.

**Kingdom already has this**: `tk ready` does the same thing. This is validated as the right pattern.

### 2. JSON Output Mode

**What beads does well**: Every command has `--json` for programmatic consumption by agents.

**Kingdom opportunity**: The `tk query` command outputs JSON, but individual commands don't. For better agent integration:

```bash
# Current: only query outputs JSON
tk query '.status == "open"'

# Could add: --json to all commands
tk ls --json
tk ready --json
```

Low priority since `tk query` already serves this need.

### 3. Typed Dependencies

**What beads does well**: Four dependency types: `blocks`, `related`, `parent-child`, `discovered-from`.

**Kingdom opportunity**: `ticket` only has `deps` (blocking) and `links` (related). The `parent` field exists but only for hierarchical display. This is probably sufficient for Kingdom's needs—the complexity of typed dependencies is overkill for a markdown-first system.

### 4. `dep tree` Visualization

**What beads does well**: `bd dep tree <id>` shows the full dependency graph.

**Kingdom already has this**: `tk dep tree <id>` does the same thing with proper tree formatting:

```
kin-a1b2 [open] Epic title
├── kin-c3d4 [in_progress] First task
│   └── kin-e5f6 [open] Subtask
└── kin-g7h8 [closed] Done task
```

### 5. Cycle Detection

**What beads does well**: Detects and reports dependency cycles.

**Kingdom already has this**: `tk dep cycle` finds cycles in open tickets:

```
Cycle 1: kin-a1b2 -> kin-c3d4 -> kin-a1b2
  kin-a1b2 [open] Task A
  kin-c3d4 [open] Task B
```

### 6. "Land the Plane" Discipline

**What beads does well**: AGENT_INSTRUCTIONS.md has a strict "land the plane" checklist requiring agents to:
1. File issues for remaining work
2. Run quality gates
3. Update issue status
4. **Push to remote** (mandatory, no exceptions)
5. Clean up git state
6. Choose follow-up work

**Kingdom opportunity**: This discipline should be adopted for Peasant completion. Currently Peasants might leave work uncommitted or unpushed. A "land the plane" checklist in Peasant instructions would prevent stale state.

### 7. External Reference Field

**What beads does well**: Issues can link to external systems (gh-123, JIRA-456).

**Kingdom already has this**: `--external-ref` flag on `tk create`.

## Patterns to Skip

### 1. SQLite + JSONL Dual Storage

**What beads does**: Maintains SQLite for fast queries, JSONL for git-tracking, with daemon sync.

**Why skip for Kingdom**: Overkill. Kingdom's `.tickets/` directory has at most dozens of tickets per feature. awk-based parsing is fast enough, and the simplicity of "it's just markdown files" makes debugging trivial. The complexity cost of maintaining dual storage isn't justified.

### 2. Background Daemon

**What beads does**: Daemon auto-exports changes, monitors for git operations, handles multi-workspace coordination.

**Why skip for Kingdom**: Kingdom's workflow is synchronous. Human talks to Hand → Hand synthesizes → Human approves → Peasant executes. There's no need for background sync. The explicit nature of "run tk, see files change" is preferable to "changes happen magically."

### 3. Agent-Specific Fields (Molecules, Wisps, Gates)

**What beads does**: Rich agent coordination primitives:
- **Molecules**: Swarm/patrol/work classification
- **Wisps**: Ephemeral messages with TTL
- **Gates**: Async coordination points

**Why skip for Kingdom**: These solve multi-agent coordination in a shared issue database. Kingdom's model is different: single Hand, single active Peasant per worktree, explicit phase transitions. The Council isn't sharing issues—it's synthesizing responses. Peasants don't need to coordinate through tickets; they work on isolated worktrees.

### 4. Hierarchical IDs (bd-a3f8.1.1)

**What beads does**: Supports epic.task.subtask notation.

**Why skip for Kingdom**: Kingdom uses `parent: <id>` field and `dep tree` visualization. Hierarchical IDs add complexity without clear benefit—especially when tickets are short-lived (feature branches).

### 5. Compaction (Memory Decay)

**What beads does**: Summarizes old closed issues to save context window.

**Why skip for Kingdom**: Kingdom's tickets live in feature branches and are relatively short-lived. When a feature ships, the branch (and its tickets) can be archived. No need for semantic compression.

### 6. Go Implementation

**What beads does**: 70k+ lines of Go for a production-grade CLI.

**Why skip for Kingdom**: The bash script is 1500 lines and does everything Kingdom needs. The maintenance burden of a Go dependency isn't justified. If Kingdom needs more sophisticated ticket tracking, the better path is improving the bash script or migrating to a Python implementation that integrates with the rest of Kingdom.

## Why Not Just Use Beads?

Beads solves: "How do I give AI agents persistent memory for long-horizon tasks across many sessions?"

Kingdom solves: "How do I coordinate multiple AI models through Design → Breakdown → Develop phases to ship features?"

Key differences:

| Concern | Beads | Kingdom |
|---------|-------|---------|
| Unit of work | Single issue | Feature (design + breakdown + tickets) |
| Agent model | Many agents, shared graph | Council + Hand + Peasants |
| Persistence | Issues survive forever | Feature branches archive |
| Complexity | High (daemon, sync, molecules) | Low (markdown files) |
| Independence | Standalone tool | Integrated with Kingdom workflow |

### What Would Break If We Used Beads

1. **Dependency**: Kingdom would depend on a Go binary that must be installed separately
2. **Complexity budget**: Debugging sync issues between SQLite/JSONL/git
3. **Over-engineering**: Features we don't need (molecules, wisps, gates, compaction)
4. **Philosophy mismatch**: Beads is about persistent state across sessions; Kingdom is about structured phases within a feature

### What We'd Gain

1. Fast queries (irrelevant at Kingdom's scale)
2. Better multi-agent coordination (Kingdom doesn't need this—we have Hand/Council)
3. Community tooling (UIs, integrations)

The tradeoff isn't worth it. Kingdom's `ticket` script is simple, sufficient, and integrated.

## Concrete Recommendations

### Adopt Now

1. **"Land the plane" checklist for Peasants**: When a Peasant completes work, it should:
   - Close the ticket
   - Run quality gates (tests, lint)
   - Commit all changes
   - Push to remote
   - Report what was completed

   Add this discipline to Peasant instructions.

2. **Blocked command**: `tk blocked` already exists and is useful. Ensure Peasants know about it for understanding what's stuck.

3. **Tags for filtering**: `tk` already supports `--tags` and filtering with `-T`. Use tags like `backend`, `frontend`, `urgent` for larger breakdowns.

### Consider Later

4. **JSON output for ls/ready**: Add `--json` flag to common commands for better tool integration. Low priority since `tk query` exists.

5. **Migrate-from-beads**: The `tk migrate-beads` command shows interoperability is possible. Could be useful if someone tries Kingdom after using beads.

### Don't Do

6. **Add SQLite**: The awk-based queries are fast enough. Adding SQLite would double the complexity.

7. **Add a daemon**: Kingdom's synchronous workflow doesn't benefit from background sync.

8. **Add agent coordination primitives**: Kingdom coordinates through Council/Hand/Peasant, not through ticket metadata.

9. **Switch to beads**: The dependency and complexity cost outweighs the benefits.

## Key Takeaways

1. **Kingdom's `ticket` script is right-sized**. It has the essential features (deps, ready, blocked, tree, cycle, links, parent) without the complexity overhead.

2. **Beads' "land the plane" discipline is valuable** and should be adopted for Peasant completion workflows.

3. **Beads solves a different problem**. It's designed for persistent agent memory across many sessions. Kingdom is designed for structured workflow phases within features.

4. **Markdown-first is a feature**. Kingdom's `.tickets/*.md` files are human-readable, git-diffable, and debuggable with basic tools. The SQLite/JSONL complexity of beads isn't necessary at Kingdom's scale.

5. **The right level of abstraction**: Beads builds infrastructure for AI-agent ecosystems. Kingdom orchestrates specific workflows. These are different layers—Kingdom could theoretically use beads underneath, but the simpler solution is better.
