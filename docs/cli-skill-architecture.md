# Design: Kingdom as CLI + Agent Skill

## Problem Statement

The current Hand implementation (`src/kingdom/hand.py`) is a Python REPL that tries to be a chat interface. But chat interfaces are hard — Claude Code, Cursor, and Codex have invested massive effort into streaming, tool visualization, progress tracking, and error handling. Kingdom's ~450 line REPL with a basic `input()` loop and spinner can't compete.

Specific pain points observed:

- **No visibility** — Can't see council conversations as they happen
- **No progress tracking** — Can't tell which models have completed vs pending
- **Command routing ambiguity** — "Write this to markdown" got routed to council instead of being a local file operation
- **Error handling** — Permission/capability errors buried in subprocess output
- **No streaming** — Batch responses only

The user's desired workflow is:

1. Talk to a coding agent (Claude Code, Cursor, etc.)
2. Consult multiple models to hammer out design
3. Break down into tickets
4. Run development loop on each ticket

The insight: **The chat interface already exists.** Kingdom shouldn't rebuild it.

## Key Reframe

The original design says:

> "The Hand is a persistent agent session that... serves as your single point of contact."

But Claude Code, Cursor, and Codex are already persistent agent sessions with great UX. Kingdom is trying to build a second, worse version of something that already exists.

Insights from third-party analysis:

- **Ralph** has no chat interface — it's a bash loop that reads from files
- **Skills** are procedural knowledge loaded into an existing agent
- **OpenClaw** treats "workspace as the durable mind" — state lives in files, not conversation

**The reframe:** The "Hand" isn't a chat interface. The Hand is **your preferred coding agent + a Kingdom skill + the kd CLI**.

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Your Coding Agent                          │
│              (Claude Code / Cursor / Codex / etc.)              │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐
│  │                    Kingdom Skill                             │
│  │  - When to consult council                                   │
│  │  - How to iterate on design.md                               │
│  │  - How to structure breakdown.md                             │
│  │  - Workflow phase transitions                                │
│  │  - How to interpret council responses                        │
│  └─────────────────────────────────────────────────────────────┘
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐
│  │                      kd CLI                                  │
│  │                                                              │
│  │  kd council ask "prompt"     → multi-model + synthesis (+logs)│
│  │  kd design show|approve      → manages design.md             │
│  │  kd breakdown show|apply     → manages breakdown + tickets   │
│  │  kd peasant start <ticket>   → spawns worker                 │
│  │  kd status                   → current state                 │
│  └─────────────────────────────────────────────────────────────┘
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │         Kingdom State          │
              │                                │
              │  .kd/runs/<feature>/           │
              │  ├── design.md      (tracked)  │
              │  ├── breakdown.md   (tracked)  │
              │  ├── learnings.md   (tracked)  │
              │  ├── state.json    (ignored)   │
              │  └── tickets/<id>/             │
              │      └── work-log.md (tracked) │
              │                                │
              │  .tickets/          (tracked)  │
              └────────────────────────────────┘
```

## What Changes

### 1. `kd chat` Becomes Optional

The Python REPL is no longer the primary interface. Users interact through their preferred coding agent (Claude Code, Cursor, etc.) which has the Kingdom skill installed.

### 2. `kd council ask` Becomes the Multi-Model Primitive

```bash
$ kd council ask "What's the best approach for OAuth refresh?"

# Returns JSON (for agent consumption):
{
  "run_id": "council-2026-02-04T18:12:09Z-4f3a",
  "synthesis": "The recommended approach combines...",
  "responses": {
    "claude": { "text": "...", "elapsed": 2.1 },
    "codex": { "text": "...", "elapsed": 1.8 },
    "agent": { "text": "...", "elapsed": 2.4 }
  },
  "paths": {
    "run_dir": ".kd/runs/oauth-refresh/logs/council/council-2026-02-04T18:12:09Z-4f3a/",
    "summary_md": ".kd/runs/oauth-refresh/logs/council/council-2026-02-04T18:12:09Z-4f3a/summary.md"
  }
}
```

The synthesis happens inside Kingdom — that's the value prop. The host agent gets one synthesized answer plus raw responses if needed, and a **run_id** that points to the saved transcripts for later inspection.

### 3. Design Iteration Moves to the Host Agent

Instead of `/design` mode in a Kingdom REPL:

```
User: "Help me design OAuth refresh handling"

Agent (with Kingdom skill):
1. Reads current .kd/runs/oauth/design.md
2. Calls: kd council ask "Given this design context: ... What should we add?"
3. Reviews synthesis and advisor outputs (via run_id if needed), updates design.md directly
4. Shows user the changes and references the council run_id
```

The skill teaches the agent when to consult council and how to structure updates. The CLI makes council outputs **findable and debuggable** even when a member fails.

### 4. Breakdown → Tickets Becomes Cleaner

```
User: "Break this down into tickets"

Agent (with Kingdom skill):
1. Reads design.md
2. Calls: kd council ask "Break this design into tickets with dependencies: ..."
3. Updates breakdown.md
4. Calls: kd breakdown --apply (with user approval)
5. Shows user the created tickets
```

### 5. The Skill Carries the Workflow Knowledge

Example skill structure:

```markdown
---
name: kingdom
description: Multi-model design and development workflow
---

# Kingdom Workflow

## Phases
1. **Design** — Iterate on design.md using council input
2. **Breakdown** — Structure tickets with dependencies
3. **Develop** — Peasants execute tickets
4. **Merge** — Human review of feature branch

## When to Use Council
- Any design decision
- Breaking down work
- Code review
- When uncertain and want multiple perspectives

## Commands
- `kd council ask "prompt"` — Get multi-model synthesis
- `kd design show` — View current design
- `kd breakdown show` — View current breakdown
- `kd breakdown --apply` — Create tickets from breakdown
- `kd status` — See current phase, tickets, state

## Design Mode
When iterating on design:
1. Read .kd/runs/<feature>/design.md
2. Consult council for significant decisions
3. Update design.md directly
4. When complete, tell user to approve
```

## Benefits

1. **UX comes for free** — Streaming, tool visualization, progress, slash commands from the host agent.

2. **Portability** — Same skill works across Claude Code, Cursor, potentially Codex.

3. **State is always external** — design.md, breakdown.md, tickets are the source of truth. No conversation state to lose.

4. **Council remains Kingdom's value** — Multi-model orchestration and synthesis is what Kingdom adds, not a chat interface.

5. **Simpler codebase** — Remove REPL logic, focus on CLI commands and skill documentation.

## What Needs Handling

### Council runs must be inspectable

Every council call writes a bundle to disk keyed by `run_id`. These live under `.kd/runs/<feature>/logs/` and are **gitignored** (operational state), but provide visibility during the session:

- `summary.md` (human-readable synthesis)
- `claude.json` / `codex.jsonl` / `agent.json` (raw responses)
- `errors.json` (if any member failed)

The durable record is the **result** of council consultation (updates to `design.md`, `breakdown.md`), not the raw council output. If you need to preserve a council run, copy the summary into `learnings.md` or reference it in the design doc.

### Session Continuity for Council Members

Currently Kingdom maintains session continuity for claude/codex/agent. Options:

- **Pass context explicitly**: Each `kd council ask` includes relevant context
- **Keep internal sessions**: `kd council ask` still uses `--resume` internally
- **Accept fresh context**: Like Ralph, each call is stateless but reads from files

Recommendation: Keep session continuity inside `kd council` — it's an implementation detail.

### Mode Awareness

Currently `/design` and `/breakdown` are modes in the REPL. With skill-based approach:

- Agent checks `kd status` to know current phase
- Skill encodes phase-appropriate behavior
- Or: `kd council ask --mode design` passes mode context automatically

### The "Write Markdown" Problem

The incident where "write this to markdown" got routed to council is an interaction design problem. With the skill approach, the simplest rule is:

- Use `kd council ask` only to get multi-model opinions.
- If the user asks to update `design.md` / `breakdown.md`, edit the file directly.
- After consulting council, reference the `run_id` so the user can inspect exactly what happened.

## CLI Contract (Draft)

### `kd council ask "prompt"`

Query all council members and return synthesized response.

```bash
kd council ask "prompt" [--json] [--no-synthesis] [--timeout SECONDS]
```

Output (JSON mode):
```json
{
  "run_id": "council-2026-02-04T18:12:09Z-4f3a",
  "synthesis": "Combined recommendation...",
  "responses": {
    "claude": { "text": "...", "error": null, "elapsed": 2.1 },
    "codex": { "text": "...", "error": null, "elapsed": 1.8 },
    "agent": { "text": "...", "error": "Timeout", "elapsed": 30.0 }
  },
  "paths": {
    "run_dir": ".kd/runs/oauth-refresh/logs/council/council-2026-02-04T18:12:09Z-4f3a/",
    "summary_md": ".kd/runs/oauth-refresh/logs/council/council-2026-02-04T18:12:09Z-4f3a/summary.md"
  }
}
```

### `kd council last`

Print the most recent council `run_id` and where the transcripts were written.

### `kd council show <run_id>`

Render a saved council run (summary + which members failed + where to read full transcripts).

### `kd council reset`

Clear all council sessions to start fresh conversation.

### `kd doctor` (or `kd council doctor`)

Quick preflight: verify required CLIs are installed and runnable (claude/codex/cursor agent), and print actionable guidance if not.

### `kd design show`

Print current design.md contents.

### `kd design approve`

Mark design as approved, transition to breakdown phase.

### `kd breakdown show`

Print current breakdown.md contents.

### `kd breakdown --apply [--yes]`

Create tickets from breakdown.md. Prompts for confirmation unless `--yes`.

### `kd status [--json]`

Show current feature, phase, ticket status.

```json
{
  "feature": "oauth-refresh",
  "phase": "breakdown",
  "design_approved": true,
  "tickets": {
    "total": 5,
    "open": 3,
    "in_progress": 1,
    "closed": 1
  }
}
```

### `kd peasant start <ticket>`

Start a peasant worker on the specified ticket.

### `kd peasant status [--json]`

Show active peasant status.

## Implementation Steps

1. **Define CLI contract** — Finalize commands, flags, JSON output formats.

2. **Add `--json` output to existing commands** — Make CLI machine-readable.

3. **Implement `kd council ask` with synthesis + run bundles** — Core multi-model primitive, plus deterministic logs keyed by `run_id`.

4. **Write the Kingdom skill** — SKILL.md teaching agents the workflow.

5. **Test with Claude Code** — Install skill, run through workflow, identify gaps.

6. **Deprecate or simplify `kd chat`** — Keep as optional fallback, not primary path.

## Open Questions

1. **Where does synthesis happen?** Inside `kd council ask` (consistent) or host agent does it (flexible)?

2. **How does the skill get installed?** Claude Code skills directory? Manual CLAUDE.md inclusion?

3. **Should `kd council ask` include design/breakdown context automatically?** Or require explicit `--context` flag?

4. **How do we handle agents that don't support skills?** Fall back to CLAUDE.md instructions?

## Relationship to Existing Docs

- **MVP.md** — Still valid. This changes *how* the workflow is driven, not *what* the workflow is.
- **council-design.md** — Subprocess architecture remains. This adds JSON output and synthesis.
- **dispatch-design.md** — The "Hand" concept evolves from "chat interface" to "skill + CLI".

## Why Not MCP?

MCP (Model Context Protocol) is for giving models access to new data sources. Kingdom isn't about data access — it's about workflow structure and multi-model orchestration. A skill (procedural knowledge) fits better than an MCP server (data provider).

## Why Not Tmux-Heavy?

Turning Kingdom into a tmux orchestrator adds complexity without solving the core UX problem. Tmux is useful for optional visibility (tailing logs), not as the primary interface.

## State and Git Integration

### Core Principle: Markdown Tracked, JSON Ignored

Simple rule for what goes in git:

- **Markdown = tracked** — durable history (design decisions, work logs, learnings)
- **JSON/JSONL = gitignored** — operational state (session IDs, raw API responses)

This keeps the repo clean while preserving an audit trail of what was decided and done.

### Directory Structure

```
.kd/
├── .gitignore                     # logs/, worktrees/, *.json, *.jsonl
├── config.json                    # repo config (optional, tracked if shared)
├── worktrees/                     # gitignored — git worktrees live here
│
└── runs/
    └── <feature>/                 # e.g., oauth-refresh
        ├── design.md              # tracked — design decisions
        ├── breakdown.md           # tracked — ticket breakdown
        ├── learnings.md           # tracked — patterns discovered (append-only)
        ├── state.json             # gitignored — current phase, sessions
        │
        ├── logs/                  # gitignored — operational logs + transcripts
        │   └── council/
        │       └── <run_id>/      # e.g., council-...-4f3a
        │           ├── summary.md
        │           ├── claude.json
        │           ├── codex.jsonl
        │           ├── agent.json
        │           └── errors.json
        │
        └── tickets/
            └── <ticket-id>/       # e.g., kin-a1b2
                ├── work-log.md    # tracked — what the peasant did
                ├── session.json   # gitignored — session state
                └── council.jsonl  # gitignored — raw council output (optional)

.tickets/                          # tracked — ticket specs (via `tk`)
```

`.kd/.gitignore`:
```
*.json
*.jsonl
runs/**/logs/
worktrees/
```

### What Gets Committed

| File | Purpose | When Updated |
|------|---------|--------------|
| `design.md` | Design decisions, rationale | During design phase |
| `breakdown.md` | Ticket structure, dependencies | During breakdown phase |
| `learnings.md` | Codebase patterns discovered | Append-only during dev |
| `tickets/<id>/work-log.md` | What the peasant did | During ticket execution |
| `.tickets/*.md` | Ticket specs, acceptance, deps | During breakdown + execution |

### What Stays Local

| File | Purpose | Why Ignored |
|------|---------|-------------|
| `state.json` | Current phase, active sessions | Operational, changes frequently |
| `session.json` | CLI session IDs for `--resume` | Machine-specific |
| `council.jsonl` | Raw council API responses | Large, operational |

### Git Workflow with Worktrees

Each ticket corresponds to a git worktree on a ticket branch:

```
main
└── feature/oauth-refresh              ← feature branch (your main checkout)
    ├── kin-a1b2/oauth-token           ← ticket branch (worktree 1)
    └── kin-c3d4/oauth-ui              ← ticket branch (worktree 2)
```

**Directory layout:**

```
~/code/kingdom/                        ← main checkout (feature branch)
├── .git/
├── .kd/runs/oauth-refresh/
│   ├── design.md
│   ├── breakdown.md
│   └── tickets/
│       ├── kin-a1b2/
│       └── kin-c3d4/
└── src/

~/code/kingdom/.kd/worktrees/oauth-refresh/
├── kin-a1b2/                          ← worktree for ticket kin-a1b2
│   ├── .git                           ← file pointing to main .git
│   └── ...
└── kin-c3d4/                          ← worktree for ticket kin-c3d4
    └── ...
```

### Merge Behavior

**Ticket branch → Feature branch:**
- Ticket's `work-log.md` merges cleanly (unique path per ticket)
- No conflicts because each ticket writes to its own directory

**Feature branch → Main:**
- Full `.kd/runs/<feature>/` history preserved
- Design, breakdown, learnings, all ticket work logs come along
- This is your audit trail

### Conflict Avoidance

1. **Single writer per file:**
   - `design.md`, `breakdown.md` — only edit on feature branch
   - `tickets/<id>/work-log.md` — only edit on that ticket's branch

2. **Append-only where possible:**
   - `learnings.md` — append patterns, never rewrite
   - `work-log.md` — append entries, never rewrite

3. **JSON not tracked:**
   - No merge conflicts on operational state
   - Each worktree has its own local state

### What Main Sees After Merge

When `feature/oauth-refresh` merges to main:

```
main:.kd/runs/oauth-refresh/
├── design.md                    # What we decided to build
├── breakdown.md                 # How we broke it down
├── learnings.md                 # What we learned
└── tickets/
    ├── kin-a1b2/
    │   └── work-log.md          # What peasant did for this ticket
    └── kin-c3d4/
        └── work-log.md          # What peasant did for this ticket
```

Anyone reviewing the repo can see the full history: what was designed, how it was broken down, and what each ticket actually did.
