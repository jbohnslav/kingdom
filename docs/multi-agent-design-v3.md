# Multi-Agent Design v3: Simplified Court Runtime

Date: 2026-02-07
Status: Proposal

## The Problem

The current system has two capabilities: **council one-shot queries** (parallel subprocess, collect, display) and **worktree creation** (`kd peasant` just makes a worktree). Everything else on the multi-agent roadmap is missing. Specifically:

1. **No persistent conversation** — council queries are conceptually isolated; "followup" exists but there's no thread identity
2. **No peasant execution** — worktrees exist but nothing runs in them
3. **No messaging** — agents can't send messages to each other or to the King asynchronously
4. **No supervision** — no status, no heartbeats, no "what are my peasants doing"

The prior design docs (gpt-pro-design, gpt-pro-v2, message-passing-design, multi-agent-system-deep-dive) converge strongly on the right architecture. They also collectively propose ~10x the current codebase in new infrastructure. This doc finds the minimum cut that unlocks the workflows we care about.

## Key Principles

1. **Files are the transport.** Messages are markdown files on disk. No sockets, no daemons, no send-keys.
2. **One runtime, multiple surfaces.** tmux is a viewer/launcher. Correctness never depends on it.
3. **Roles are config, not code paths.** Council members and peasants are both agents with different defaults.
4. **The King reads raw.** Council responses are presented as-is. The Hand doesn't filter or summarize advisor opinions.
5. **The Hand is the Lead.** The Hand (the King's primary coding agent) acts as team lead for peasants — spawning workers, monitoring progress, sending feedback, and handling escalations. The King delegates supervision to the Hand and intervenes only when needed.

## What We're Cutting (for v1)

The prior docs propose a lot of machinery that's premature for a 3,500-line codebase:

| Proposed | Decision |
|----------|----------|
| ULID-based message IDs | Sequential numbering is fine |
| inbox/processing/outbox directories per agent | Single messages directory per thread |
| events.jsonl event ledger | state.json per branch is enough |
| Heartbeat files polled every 2-5s | Check process liveness directly (pid) |
| Channel definitions with routing patterns | Hardcode the two patterns we need |
| Atomic claim with file locking | One process per agent, no races to solve |
| `kd watch` Rich Live dashboard | `kd status` with agent info is enough |
| Separate foreman agent | The Hand fills this role; no separate agent needed |
| Queue semantics (followup/collect/interrupt) | Just followup |
| Permission profiles (headless vs attached) | Use per-backend skip-permissions flags |

This isn't "we'll never need these." It's "we don't need them before we have working peasants."

## The Design

### Core Concept: Everything is a Thread

A **thread** is a named conversation between agents. Council discussions are threads. Peasant work sessions are threads. DMs to one advisor are threads. One primitive.

```
.kd/branches/<branch>/threads/
  <thread-id>/
    thread.json          # metadata (gitignored by *.json)
    0001-king.md         # messages (tracked)
    0002-claude.md
    0003-codex.md
    0004-cursor.md
    0005-king.md         # follow-up
    0006-claude.md       # response
```

A thread has:
- **id** (human-readable slug, e.g. `council-caching-debate`, `kin-042-work`)
- **members** (list of agent names)
- **pattern** (`council` = broadcast-collect, `work` = supervised, `direct` = 1:1)

Message files are simple markdown with minimal frontmatter:

```yaml
---
from: king
to: all           # or "claude", "codex", etc.
timestamp: 2026-02-07T15:30:12Z
refs:
  - .kd/branches/feature-auth/design.md
---

What's the right caching strategy here?
```

### Agent Config

Agent definitions are markdown with frontmatter, same format as tickets. Two file types across the whole project: `.md` (tracked) and `.json` (gitignored).

```
.kd/agents/
  claude.md
  codex.md
  cursor.md
```

```markdown
---
name: claude
backend: claude_code
cli: claude --print --output-format json
resume_flag: --resume
---
```

Peasant agents are **ephemeral** — created when `kd peasant start` runs, removed when done. No need to pre-register them.

### State (runtime)

All agent runtime state lives in the existing `state.json` per branch (already gitignored). No separate session files.

```json
{
  "agents": {
    "claude": {
      "resume_id": "abc123",
      "status": "idle"
    },
    "codex": {
      "resume_id": "def456",
      "status": "idle"
    },
    "peasant-kin-042": {
      "resume_id": "ghi789",
      "status": "working",
      "pid": 12345,
      "ticket": "kin-042",
      "thread": "kin-042-work",
      "started_at": "2026-02-07T15:30:00Z",
      "last_activity": "2026-02-07T15:44:00Z"
    }
  },
  "current_thread": "council-caching-debate"
}
```

Agent status is one of: `idle`, `working`, `blocked`, `done`, `failed`.

### Full File Layout

```
.kd/
  .gitignore                           # *.json, *.log, **/logs/, etc.
  agents/                              # NEW — agent definitions (tracked, .md)
    claude.md
    codex.md
    cursor.md
  branches/<branch>/
    design.md                          # existing (tracked)
    tickets/                           # existing (tracked)
    threads/                           # NEW — all conversations (tracked, .md)
      council-caching-debate/
        thread.json                    #   metadata (gitignored)
        0001-king.md                   #   messages (tracked)
        0002-claude.md
        0003-codex.md
      kin-042-work/
        thread.json
        0001-king.md
        0002-peasant-kin-042.md
    logs/                              # existing (gitignored)
      peasant-kin-042/                 #   NEW — peasant subprocess output
        stdout.log
        stderr.log
    state.json                         # existing (gitignored) — agents, threads, all runtime
  backlog/tickets/                     # existing (tracked)
  archive/                             # existing
  worktrees/                           # existing (gitignored)
```

Two file types: `.md` is tracked, `.json`/`.log` is gitignored. No new gitignore rules needed.

### The Hand as Lead

The Hand is the King's primary coding agent — Claude Code, Cursor, etc. The King works inside the Hand's TUI. In the multi-agent system, the Hand acts as **team lead** for peasants, analogous to the "lead" in Claude Teams.

**What the Hand does as Lead:**
- Spawns peasants on ready tickets (`kd peasant start`)
- Monitors their progress (`kd peasant status`)
- Reads escalations and responds (`kd peasant read`, `kd peasant msg`)
- Reviews completed work and runs quality gates (`kd peasant review`)
- Sends feedback when work isn't done ("tests are failing, fix X")
- Approves completion or bounces back with reasons

**What the Hand does NOT do:**
- Synthesize or filter council opinions (King reads those raw)
- Make design decisions on behalf of the King
- Autonomously start work without the King's direction

**How it works in practice:**

The King says "spin up peasants on the ready tickets and manage them." The Hand takes it from there:

```
King: start peasants on the ready tickets and keep them on track

  Hand runs: kd ticket ready
  > KIN-042  oauth token refresh     (no deps)
  > KIN-043  oauth UI components     (no deps)

  Hand runs: kd peasant start KIN-042
  Hand runs: kd peasant start KIN-043
  > Started peasant-KIN-042 (claude, working)
  > Started peasant-KIN-043 (claude, working)

  ... later ...

  Hand runs: kd peasant status
  > KIN-042  working   14m   no escalations
  > KIN-043  blocked    8m   "need clarification on token format"

  Hand runs: kd peasant read KIN-043
  > peasant-KIN-043: "The ticket says 'standard token format' but the
  > existing code uses both JWT and opaque tokens. Which should I use?"

  Hand runs: kd peasant msg KIN-043 "Use JWT. Match the pattern in auth/tokens.py"
```

The King watches this happen in their terminal. They can interject ("actually use opaque tokens") or let the Hand handle it. The Hand is the messenger and supervisor, but the King has full visibility and override.

**The key distinction from Claude Teams:** In Teams, the lead synthesizes results from all teammates. In Kingdom, the Hand leads *peasants* (workers) but does not mediate *council* (advisors). The King reads council output directly. This preserves the "multiple independent perspectives" value of the council.

`kd peasant manage` is the Hand's main entry point for supervision — it shows what needs attention:

```bash
kd peasant manage
# Pending escalations:
#   KIN-043  "need clarification on token format"      3m ago
#
# Ready for review:
#   KIN-042  4 commits, tests passing                  1m ago
#
# Stale (no activity >10m):
#   (none)
#
# Ready tickets (not yet started):
#   KIN-044  user settings page
```

### Command Surface

**Council — the unified conversation interface:**

```bash
# Council (broadcast to all advisors)
kd council ask "Should we use Redis?"              # new thread, all members
kd council ask --to codex "Elaborate on pooling"   # same thread, one member
kd council ask "Final recommendations?"            # same thread, all members
kd council ask --thread new "Different topic"      # explicit new thread

kd council show [thread-id]                        # show thread history
kd council list                                    # list threads
```

The current `kd council ask` / `kd council followup` / `kd council critique` collapse into one command. `ask` defaults to "continue current thread" if one exists, or "start new thread" if not. `--to` targets a specific member.

**Peasant execution:**

```bash
kd peasant start KIN-042 [--agent claude]  # create worktree + launch agent
kd peasant status                           # table of active peasants
kd peasant manage                           # what needs attention (Hand's main loop)
kd peasant logs KIN-042 [--follow]          # tail logs
kd peasant msg KIN-042 "Focus on tests"     # send directive
kd peasant read KIN-042                     # read escalations
kd peasant review KIN-042                   # review work + run quality gates
kd peasant stop KIN-042                     # stop the agent process
```

`kd peasant start` does what the current `kd peasant` does (worktree + branch) plus:
1. Registers `peasant-KIN-042` in `state.json`
2. Creates a `kin-042-work` thread with members `[peasant-kin-042, king]`
3. Seeds the thread with a `ticket_start` message (ticket content, acceptance criteria, refs)
4. Launches the backend agent as a subprocess in the worktree
5. Captures stdout/stderr to log files

**Status overview:**

```bash
kd status
# Shows: branch, design/breakdown status, tickets, active agents, unread messages
```

### How Peasants Actually Work

The agent process is a subprocess running the backend CLI. For Claude:

```bash
claude --print --output-format json \
  --resume $SESSION_ID \
  -p "$(cat ticket_prompt.md)" \
  2>stderr.log
```

The **harness** is a thin Python wrapper (`kd agent run`) that:
1. Builds the prompt from ticket + acceptance criteria
2. Launches the subprocess
3. Captures output
4. Parses the response
5. Updates `state.json` (status, resume_id, last_activity)
6. Writes the response as a message to the thread
7. Checks for escalations or completion signals

For v1, the harness runs **one turn at a time**. The peasant does one chunk of work, reports back, and the King can review + send another directive. This is simpler than a fully autonomous loop and matches how the backends actually work (one-shot with `--print`).

Autonomous multi-turn loop is v2.

### Quality Gates

On `kd peasant done KIN-042` (or when the peasant signals completion):

1. Run `pytest` in the worktree
2. Run `ruff check`
3. Check acceptance criteria (present in ticket)

If gates fail, the peasant gets a feedback message and stays `working`. This is the Teams-inspired pattern. Implement as a simple function call for v1; hook system with exit codes is v2.

## What We're NOT Building (v1)

- No daemon/server process
- No `kd watch` live dashboard (use `kd status` + `kd peasant status` + `kd peasant manage`)
- No tmux automation (launch agents in background; user can tmux manually)
- No autonomous agent-to-agent messaging (peasants talk to King/Hand, not to each other)
- No separate foreman agent (the Hand fills this role)
- No event ledger
- No channel abstraction
- No complex permission system

## Build Order

### Phase 1: Threads + council UX

- Add thread model (thread.json + messages/)
- Refactor `kd council ask` to use threads
- Merge `ask`/`followup`/`critique` into unified `ask` with `--to`
- `kd council show` / `kd council list`

This immediately improves the council experience with minimal code.

### Phase 2: Peasant execution

- Agent state in state.json + logs
- `kd agent run` harness command
- `kd peasant start` (worktree + launch agent)
- `kd peasant status` / `kd peasant logs` / `kd peasant stop`
- Simple quality gates on completion

This is the real unlock — actual parallel work.

### Phase 3: Hand as Lead (messaging + supervision)

- `kd peasant msg` / `kd peasant read` (Hand sends directives, reads escalations)
- `kd peasant manage` (what needs attention — escalations, reviews, stale workers, ready tickets)
- `kd peasant review` (Hand reviews work + runs quality gates)
- Peasant escalation detection (agent writes a marker file, harness picks it up)
- `kd status` integration (show active agents + unread messages)

This is where the Hand becomes a real team lead, not just a command executor.

### Phase 4: Polish + autonomy

- Autonomous peasant loop (multi-turn without Hand intervention)
- Hand-driven autonomous supervision (Hand runs manage loop without King prompting)
- Better status display
- `kd watch` if needed
- tmux adapter if needed

## References

Prior design docs (archived to `docs/archive/`):

- `gpt-pro-design.md` — Protocol/runtime/UX layer separation, agent sessions with mailboxes, worker loop model
- `gpt-pro-v2.md` — Synthesized court runtime proposal, event ledger, quality gates, migration plan
- `message-passing-design.md` — Court unified agent model, channels/routing patterns, message-as-primitive
- `multi-agent-system-deep-dive.md` — Option analysis, CLI-first architecture, tmux guidance, permission profiles
