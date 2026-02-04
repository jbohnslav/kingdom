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

## Roles: King, Hand, and Council

Understanding the metaphor is critical to understanding the workflow:

- **King** = You (the human). Final decision-maker. Reads council advice directly.
- **Hand** = Your primary coding agent (Claude Code, Cursor, etc.). Always at your side. Executes your decisions.
- **Council** = Other models (GPT, Gemini, etc.). Advisors you consult for outside perspectives your Hand might miss.

**Why this matters:** The point of the Council is to get perspectives *different from your Hand*. If the Hand auto-synthesizes council responses, you're filtering outside perspectives through the same agent you always use—defeating the purpose.

**The flow:**
```
King works with Hand (normal coding workflow)
    ↓
King wants outside perspectives
    ↓
King runs: kd council ask "..."
    ↓
Council members respond DIRECTLY to King (not filtered by Hand)
    ↓
King reads all responses, decides what to adopt
    ↓
King tells Hand what to do
```

The Council provides perspectives. The King decides. The Hand executes.

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
              │  └── tickets/                   │
              │      └── kin-*.md   (tracked)  │
              └────────────────────────────────┘
```

## What Changes

### 1. `kd chat` Becomes Optional

The Python REPL is no longer the primary interface. Users interact through their preferred coding agent (Claude Code, Cursor, etc.) which has the Kingdom skill installed.

### 2. `kd council ask` Becomes the Multi-Model Primitive

```bash
$ kd council ask "What's the best approach for OAuth refresh?"
```

**No auto-synthesis.** The King reads council responses directly and decides what to adopt. This is the core value prop: getting perspectives *outside* your Hand's viewpoint.

#### Terminal Output (Rich-based)

Council responses are displayed using [Rich](https://rich.readthedocs.io/) for readable terminal output:

```
╭─────────────────────── claude ───────────────────────╮
│ For OAuth refresh, I recommend JWT with sliding      │
│ expiration. The key insight is that you want to      │
│ refresh proactively, not reactively...               │
│                                                      │
│ ```python                                            │
│ def refresh_token(self):                             │
│     if self.expires_at < now() + BUFFER:             │
│         return self.client.refresh()                 │
│ ```                                                  │
╰──────────────────────────────────────────────────────╯

╭─────────────────────── gemini ───────────────────────╮
│ Token rotation is the critical pattern here. The     │
│ upstream API supports refresh token rotation, which  │
│ means each refresh returns a new refresh token...    │
╰──────────────────────────────────────────────────────╯

╭──────────────────────── gpt ─────────────────────────╮
│ I found the `backoff` library which handles retry    │
│ with exponential backoff elegantly. Combined with    │
│ refresh-ahead pattern...                             │
╰──────────────────────────────────────────────────────╯

Saved to: .kd/runs/oauth/council/run-4f3a/
```

**Why top-to-bottom panels (not side-by-side):**
- Full terminal width for each response
- Long responses and code blocks stay readable
- Hand can still parse output if needed (clear panel headers)
- Side-by-side falls apart with 3+ models and real content

**Rich features used:**
- `Panel` with model name as title
- `Markdown` rendering inside panels (syntax highlighting for free)
- `Progress` / `Spinner` showing which models are still running

#### File Output (Always)

Every council call saves responses to disk:

```
.kd/runs/<feature>/logs/council/<run_id>/
├── claude.md      # Full response
├── gemini.md      # Full response
├── gpt.md         # Full response
├── metadata.json  # Timing, errors, model versions
└── errors.json    # If any member failed
```

The King reads in terminal for quick review. Files persist for:
- Re-reading longer responses
- Hand referencing when King says "use Gemini's approach from the council output"
- Debugging when something goes wrong

### 3. Design Iteration: King Reads Council Directly

Instead of `/design` mode in a Kingdom REPL, and instead of Hand filtering council responses:

```
King: "I want to design OAuth refresh handling"

King: kd council ask "What's the best approach for OAuth token refresh?"
      # Reads all three responses in Rich panels
      # Thinks: "I like Gemini's token rotation, GPT's backoff library,
      #          but Claude's refresh-ahead timing logic is cleanest"

King (to Hand): "Write the design using Claude's refresh-ahead approach
                 with Gemini's token rotation pattern. Add the backoff
                 library GPT found for retry logic."

Hand: Updates design.md with the combined approach
```

**Key insight:** The King does the synthesis mentally, then directs the Hand. This preserves the value of outside perspectives—they're not filtered through the same agent that would have answered anyway.

The CLI makes council outputs **findable and debuggable**. The files at `.kd/runs/.../council/<run_id>/` let Hand reference exactly what each council member said.

### 4. Breakdown → Tickets Becomes Cleaner

```
King: "I want to break this design into tickets"

King: kd council ask "Break this design into tickets with dependencies: [design.md context]"
      # Reads council responses showing different breakdown approaches
      # Decides: "Gemini's 4-ticket structure makes sense, but GPT caught
      #           a dependency Claude missed"

King (to Hand): "Create the breakdown using Gemini's structure but add
                 the dependency GPT identified between auth and storage"

Hand: Updates breakdown.md, runs kd breakdown --apply
```

The King sees multiple perspectives on how to structure the work, then directs the Hand.

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
- Any design decision where you want outside perspectives
- Breaking down work (multiple viewpoints on ticket structure)
- Code review (catch things your Hand might miss)
- When uncertain and want to see how different models approach the problem

## Commands
- `kd council ask "prompt"` — Get perspectives from multiple models (you read and decide)
- `kd council <member> "prompt"` — Follow up with specific council member
- `kd council critique` — Have members evaluate each other's responses
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

4. **Council remains Kingdom's value** — Multi-model orchestration and direct access to outside perspectives is what Kingdom adds, not a chat interface or auto-synthesis.

5. **Simpler codebase** — Remove REPL logic, focus on CLI commands and skill documentation.

## What Needs Handling

### Council runs must be inspectable

Every council call writes a bundle to disk keyed by `run_id`. These live under `.kd/runs/<feature>/logs/council/` and are **gitignored** (operational state), but provide visibility during the session:

- `claude.md` / `gemini.md` / `gpt.md` — Full responses in Markdown (readable, Hand can reference)
- `metadata.json` — Timing, model versions, token counts
- `errors.json` — If any member failed
- `critiques/` — If `kd council critique` was run

No `summary.md` or synthesis file—the King reads responses directly and synthesizes mentally.

The durable record is the **result** of council consultation (updates to `design.md`, `breakdown.md`), not the raw council output. If you need to preserve insights from a council run, incorporate them into `design.md` or `learnings.md`.

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

Query all council members. **No auto-synthesis**—King reads responses directly.

```bash
kd council ask "prompt" [--json] [--timeout SECONDS] [--open]
```

**Default output:** Rich panels to terminal (see above) + files saved to disk.

**Flags:**
- `--json` — Machine-readable output for scripting
- `--timeout SECONDS` — Per-model timeout (default: 120)
- `--open` — After saving, open response directory in `$EDITOR`

Output (JSON mode):
```json
{
  "run_id": "council-2026-02-04T18:12:09Z-4f3a",
  "responses": {
    "claude": { "text": "...", "error": null, "elapsed": 2.1 },
    "gemini": { "text": "...", "error": null, "elapsed": 1.8 },
    "gpt": { "text": "...", "error": "Timeout", "elapsed": 30.0 }
  },
  "paths": {
    "run_dir": ".kd/runs/oauth-refresh/logs/council/council-2026-02-04T18:12:09Z-4f3a/",
    "responses": {
      "claude": ".kd/runs/.../claude.md",
      "gemini": ".kd/runs/.../gemini.md",
      "gpt": ".kd/runs/.../gpt.md"
    }
  }
}
```

Note: No `synthesis` field. King synthesizes by reading and deciding.

### `kd council <member> "prompt"`

Follow up with a specific council member within the session.

```bash
kd council gemini "What about offline scenarios?"
kd council gpt "Show me how to use that backoff library"
```

Useful for iterating with one advisor before deciding. Each follow-up appends to that member's response file.

### `kd council critique`

Have council members anonymously evaluate each other's responses (inspired by LLM Council's Stage 2).

```bash
kd council critique [--run-id <id>]
```

Each member receives all responses anonymized ("Response A", "Response B") and identifies strengths/weaknesses. Useful for high-stakes decisions where you want models to check each other.

Output: Rich panels showing each member's critique, saved to `<run_id>/critiques/`.

### `kd council last`

Print the most recent council `run_id` and paths to response files.

```bash
$ kd council last
run-4f3a (2026-02-04 18:12:09)
  .kd/runs/oauth/council/run-4f3a/
  ├── claude.md
  ├── gemini.md
  └── gpt.md
```

### `kd council show <run_id>`

Re-render a saved council run in Rich panels. Useful for re-reading previous consultations.

### `kd council reset`

Clear all council sessions to start fresh conversation (new context for all members).

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

3. **Implement `kd council ask` with Rich output + run bundles** — Core multi-model primitive with Rich panels for terminal display, Markdown files for persistence.

4. **Add `kd council <member>` for follow-ups** — Individual member iteration within session.

5. **Add `kd council critique`** — Optional peer evaluation command.

6. **Write the Kingdom skill** — SKILL.md teaching agents the workflow (including when to suggest council consultation).

7. **Test with Claude Code** — Install skill, run through workflow, identify gaps.

8. **Deprecate or simplify `kd chat`** — Keep as optional fallback, not primary path.

## Open Questions

1. ~~**Where does synthesis happen?**~~ **Resolved:** The King synthesizes mentally by reading council responses, then directs the Hand. No auto-synthesis—that would filter outside perspectives through your primary agent, defeating the purpose.

2. **How does the skill get installed?** Claude Code skills directory? Manual CLAUDE.md inclusion?

3. **Should `kd council ask` include design/breakdown context automatically?** Or require explicit `--context` flag? (Leaning toward: include current phase context by default, with `--no-context` to disable.)

4. **How do we handle agents that don't support skills?** Fall back to CLAUDE.md instructions?

5. **Should `kd council critique` be automatic or opt-in?** Current design: opt-in via explicit command. Auto-critique would add latency and cost for every council call.

## Relationship to Existing Docs

- **MVP.md** — Still valid. This changes *how* the workflow is driven, not *what* the workflow is.
- **council-design.md** — Subprocess architecture remains. This adds Rich terminal output and removes auto-synthesis (King reads directly).
- **dispatch-design.md** — The "Hand" concept evolves from "chat interface" to "skill + CLI".
- **third_party/llm-council.md** — Analysis of LLM Council project. Adopted: transparent deliberation, graceful degradation, inspectable outputs. Skipped: auto-synthesis (King is the chairman).

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
        │       └── <run_id>/      # e.g., run-4f3a
        │           ├── claude.md      # Full response (Markdown)
        │           ├── gemini.md      # Full response (Markdown)
        │           ├── gpt.md         # Full response (Markdown)
        │           ├── metadata.json  # Timing, model versions
        │           ├── errors.json    # If any member failed
        │           └── critiques/     # If critique was run
        │               ├── claude.md
        │               ├── gemini.md
        │               └── gpt.md
        │
        └── tickets/
            └── tickets/
                └── kin-*.md       # tracked — ticket specs (via `kd ticket`)
```

`.kd/.gitignore`:
```
*.json
*.jsonl
**/logs/
**/sessions/
worktrees/
current
```

### What Gets Committed

| File | Purpose | When Updated |
|------|---------|--------------|
| `design.md` | Design decisions, rationale | During design phase |
| `breakdown.md` | Ticket structure, dependencies | During breakdown phase |
| `learnings.md` | Codebase patterns discovered | Append-only during dev |
| `tickets/*.md` | Ticket specs, acceptance, deps | During breakdown + execution |

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
