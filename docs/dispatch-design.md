# Kingdom: Semi-Automated Agentic Development Workflow

A structured workflow for AI-assisted software development that automates execution while keeping humans in the loop at critical decision points.

## Overview

Kingdom sits between "manually babysitting Claude Code" and "full autonomous agents." It automates ticket execution, testing, and review while preserving human oversight for design decisions and final approval.

The system uses a **Hand** - a persistent agent session that orchestrates the entire workflow, manages Peasants, and serves as your single point of contact. You (the King) describe what you want; the Hand handles the details.

Agent communication is coordinated through a dedicated tmux server, allowing humans and agents to attach to any session as needed.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW STAGES                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐           │
│   │  DESIGN  │────▶│   PLAN   │────▶│ DEVELOP  │────▶│  MERGE   │           │
│   │(Council) │     │(Council) │     │(Peasants)│     │  (King)  │           │
│   └──────────┘     └──────────┘     └──────────┘     └──────────┘           │
│        │                │                │                │                 │
│        ▼                ▼                │                ▼                 │
│   [King Review]    [King Review]         │           main branch            │
│                                          │                                  │
│                                          ▼                                  │
│                                 ┌─────────────────┐                         │
│                                 │  Per-Ticket Loop │                        │
│                                 │  (fresh agents)  │                        │
│                                 │                  │                        │
│                                 │  dev → test →   │                         │
│                                 │  review → merge │                         │
│                                 │  to feature     │                         │
│                                 └─────────────────┘                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Concepts

### The Hand

The Hand is a persistent agent session that:

- Has full context: design doc, tickets, Peasant status, conversation history
- Manages the workflow by coordinating phase transitions
- Monitors Peasants and handles blockers
- Asks you (the King) questions when human judgment is needed
- Can add/modify tickets, pause Peasants, revise designs mid-flight

You don't need to remember what to do next. The Hand tells you what's happening and asks when it needs input.

### The Council

The council provides multi-model consensus for important decisions:

1. Your prompt goes to 3 frontier models in parallel (e.g., Claude, GPT, Gemini)
2. Each model responds independently
3. A synthesis model combines the best insights
4. You can direct the synthesis or iterate

**Council is mandatory for:**

- Design phase
- Plan phase
- Code review (within each ticket's loop)

**Council is optional for:**

- Mid-work conversations with the mayor (mayor invokes it as a tool when needed)

### Ticket Management

We use [ticket](https://github.com/wedow/ticket) (`tk`) for tracking work:

- Single bash script, no runtime dependencies
- Markdown files with YAML frontmatter - human readable, grep-able
- Built-in dependency graph (`tk dep`, `tk ready`, `tk blocked`)
- No daemon, no database, no sync issues

Peasants use `tk` commands to update ticket status and log their work.

**Core Commands:**

```bash
tk create "Implement OAuth refresh" -p 1 -d "Description here"
tk dep nw-5c46 nw-3a21  # 5c46 depends on 3a21
tk ready                 # Tickets with all deps resolved
tk start nw-5c46        # Mark in_progress
tk close nw-5c46        # Mark closed
tk dep tree nw-5c46     # View dependency tree
```

### Git Branching Strategy

```
main
└── feature/oauth-refresh           ← feature branch (created at start)
    ├── nw-5c46/oauth-refresh       ← ticket branch
    ├── nw-3a21/token-storage       ← ticket branch
    └── nw-7b89/refresh-ui          ← ticket branch
```

- Feature branch created when you start work
- Each ticket gets its own branch off the feature branch
- Tickets merge to feature branch after passing review + CI
- Feature branch merges to main only after human review

---

## Stage 1: Design (Council)

**Goal:** Produce a high-quality design document through multi-model consensus.

**Process:**

1. You (the King) describe what you want to build to the Hand
2. Hand routes your requirements to the Council (3 models in parallel)
3. Each model drafts a design approach
4. Synthesis model combines the best insights
5. You iterate with the Council until satisfied
6. Hand saves the final design document

**Artifacts:**

- `design.md` - The final design document

**King Checkpoint:** Review and approve the design before proceeding to planning.

## Stage 2: Plan (Council)

**Goal:** Break the design into executable tickets with dependency relationships.

**Process:**

1. Hand presents the design to the Council
2. Council decomposes into discrete tickets
3. Identifies dependencies (what blocks what)
4. Assigns tickets as serial or parallelizable
5. Hand creates tickets using `tk` CLI
6. You (the King) review the breakdown and adjust as needed

**Ticket Structure:**

```yaml
---
id: nw-5c46
title: Implement OAuth token refresh
status: open
priority: 1
depends_on:
  - nw-3a21  # Auth service refactor must complete first
branch: nw-5c46/oauth-refresh
---

## Description

Implement automatic token refresh when access tokens expire...

## Acceptance Criteria

- [ ] Refresh triggers 5 minutes before expiry
- [ ] Failed refresh redirects to login
- [ ] Refresh token rotation is supported

## Work Log

(Populated during execution by dev agent)

## Test Results

(Populated by test agent)

## Review Comments

(Populated by review council)
```

**Artifacts:**

- `.tickets/*.md` - Individual ticket files
- Dependency graph viewable via `tk dep tree`

**King Checkpoint:** Review ticket breakdown and dependencies before execution begins. Confirm number of parallel Peasants.

## Stage 3: Develop (Parallel Peasants)

**Goal:** Execute tickets through a dev→test→review loop with fresh agents at each phase.

**Process:**

1. Hand runs `tk ready` to find unblocked tickets
2. For each ready ticket, assigns it to an available Peasant
3. Peasant executes the per-ticket loop (see below)
4. On success, ticket branch merges to feature branch
5. Hand picks up next ready ticket

### Per-Ticket Loop

Each ticket flows through this loop, with a **fresh agent** (cleared context) at each phase:

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│   DEV   │────▶│  TEST   │────▶│ REVIEW  │
│ (agent) │     │ (agent) │     │(council)│
└─────────┘     └─────────┘     └─────────┘
     ▲                               │
     │         fail                  │
     └───────────────────────────────┘
                               pass ↓
                          ┌─────────────┐
                          │  CI + Merge │
                          │ to feature  │
                          └─────────────┘
```

**Dev Phase (fresh agent):**

- Reads: design doc, ticket description, acceptance criteria
- Implements the feature
- Updates work log throughout execution
- Commits to ticket branch
- Uses `tk` to update ticket status

**Test Phase (fresh agent):**

- Reads: design doc, ticket + work log, code diff
- Writes tests covering:
  - Happy path from acceptance criteria
  - Edge cases
  - Error handling
- Records test results in ticket
- Commits tests to ticket branch

**Review Phase (council):**

- Each council model reads: design doc, ticket, full diff, test results
- Reviews for:
  - Correctness against design and acceptance criteria
  - Security vulnerabilities
  - Code quality and style
  - Test coverage
- Synthesis produces pass/fail decision with comments
- If fail: returns to dev phase with review comments
- If pass: proceeds to merge

**Merge Gate:**

- Must pass council code review
- Must pass CI (tests, linting, etc.)
- Auto-merges ticket branch to feature branch

**Work Log Convention:**

```markdown
## Work Log

- 2026-01-24 14:32: Started implementation, reading existing auth code
- 2026-01-24 14:45: **ROADBLOCK** - TokenService interface doesn't expose refresh method
- 2026-01-24 14:52: Resolution: Added refreshToken() to interface, updated implementations
- 2026-01-24 15:10: Core logic complete, moving to test phase
```

**Parallelization:**

- Tickets without dependencies can execute simultaneously
- Each Peasant operates in its own git worktree
- No shared mutable state between Peasants

## Stage 4: Merge (King Review)

**Goal:** Merge the completed feature branch to main after King review.

**Process:**

1. All tickets complete and merged to feature branch
2. Hand notifies you that the feature is ready for review
3. You (the King) review the complete feature branch
4. May create new tickets for fixes/refactors (returns to Stage 3)
5. When satisfied, approve merge to main
6. Hand merges feature branch to main

**Artifacts:**

- Feature branch with all changes
- Merge commit to main
- Closed tickets

**King Checkpoint:** This is the final gate. Review the complete feature before it reaches main.

---

## Handling Changes Mid-Flight

Real development isn't linear. The Hand handles changes gracefully:

**Adding a ticket:**

- You (the King) describe the new work to the Hand
- Hand creates the ticket with `tk`, sets dependencies
- A free Peasant picks it up based on priority

**Design flaw discovered:**

- Hand can pause affected Peasants
- Drafts revised approach (optionally via Council)
- Updates affected tickets
- Resumes work

**Bug found unrelated to feature:**

- Add as low-priority ticket to current work, or
- Handle outside this feature (your choice)

**Peasant stuck:**

- Hand monitors for roadblocks
- Can reassign work, provide guidance, or escalate to you (the King)

---

## Approvals and Escalations

Even in autopilot, some things need the King's judgment:

1. **Dangerous operations:** Migrations, external API calls, destructive commands
2. **Blockers:** Design ambiguity, unclear requirements, repeated test failures
3. **Resource decisions:** API keys, environment configuration

When these occur:

- Hand surfaces them in status and in chat
- You (the King) can quick-approve or discuss with the Hand
- Or attach directly to a Peasant to intervene

---

## File Structure

```
.tickets/
├── nw-3a21 - Auth service refactor.md
├── nw-5c46 - Implement OAuth refresh.md
├── nw-7b89 - Update login UI.md
└── ...

.kd/
├── current                     # Pointer to active feature
├── config.json                 # Global config (model settings, Peasant count)
└── runs/
    └── oauth-refresh/
        ├── state.json          # Phase, Peasant assignments, tmux sessions
        ├── design.md           # Design document
        └── logs/               # Agent logs, escalations

.kd/worktrees/
├── peasant-1/                  # Git worktree for Peasant 1
├── peasant-2/                  # Git worktree for Peasant 2
└── peasant-3/                  # Git worktree for Peasant 3
```

---

## Open Questions

1. **Stuck detection:** How does the Hand know a Peasant is stuck vs. working on something hard? Token budget? Time limit? Explicit signal?

2. **Context handoff:** When a ticket requires multiple dev→review cycles, how much context survives? Full work log as reference?

3. **Conflict resolution:** What counts as a "trivial" conflict for auto-resolution during merge to feature branch?

4. **Parallelism limits:** How many simultaneous Peasants before resource contention (API rate limits, git operations) becomes a problem?

5. **Rollback strategy:** If a ticket's implementation is bad after merge to feature, can we surgically revert just that ticket?

---

## Alternatives Considered

### Beads (steveyegge/beads)

A git-backed issue tracker with SQLite caching and background daemon for auto-sync.

**Why not:**

- Background daemon causes sync issues (multiple databases, worktrees falling out of sync)
- JSONL format puts large chunks into agent context
- Reports of Claude ignoring beads or corrupting the database

### Beans (hmans/beans)

Flat-file markdown tracker with GraphQL query engine and TUI.

**Why not:**

- Still in 0.1.x with frequent breaking changes
- No built-in `ready` command for dependency-based work selection

### Backlog.md (MrLesk/Backlog.md)

Full-featured project management with web UI, MCP integration.

**Why not:**

- Heavy - many features we won't use
- Bun/Node dependency vs pure bash
- Web UI adds server process and potential state drift

### Why ticket wins

1. Simplest possible storage layer
2. Failure modes are obvious (it's just files)
3. We define the conventions (work logs, branch naming) in our workflow
4. Nothing running in the background that can desync
5. Easy to extend if needed

---

## Implementation Phases

### Phase 1: Manual orchestration with ticket

- Set up `ticket` in repo
- Define ticket template with work log section
- Manually run the workflow end-to-end
- Document friction points

### Phase 2: Mayor and council

- Implement mayor as persistent agent session
- Build council multi-model consensus flow
- Design and plan phases working

### Phase 3: Worker orchestration

- Spawn workers in git worktrees
- Per-ticket loop with fresh agents
- Basic progress monitoring via `tk`

### Phase 4: Review and merge automation

- Council-based code review
- CI integration
- Automated merge to feature branch

### Phase 5: Supervision and resilience

- Stuck detection
- Automatic context refresh on long-running tickets
- Human escalation paths
