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
| Atomic claim with file locking | Per-agent session files, no shared writes |
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

Per-agent runtime state lives in `sessions/` — one JSON file per agent. Each agent writes only its own file, so no locking is needed. Branch-level state (current thread pointer) stays in `state.json`.

`sessions/claude.json`:
```json
{
  "resume_id": "abc123",
  "status": "idle"
}
```

`sessions/peasant-kin-042.json`:
```json
{
  "resume_id": "ghi789",
  "status": "working",
  "pid": 12345,
  "ticket": "kin-042",
  "thread": "kin-042-work",
  "started_at": "2026-02-07T15:30:00Z",
  "last_activity": "2026-02-07T15:44:00Z"
}
```

`state.json`:
```json
{
  "current_thread": "council-caching-debate"
}
```

Agent status is one of: `idle`, `working`, `blocked`, `done`, `failed`, `stopped`.

### Full File Layout

```
.kd/
  .gitignore                           # *.json, *.log, **/logs/, **/sessions/, etc.
  agents/                              # who your agents are (tracked)
    claude.md
    codex.md
    cursor.md
  branches/<branch>/
    design.md                          # the plan (tracked)
    tickets/                           # work items (tracked)
    threads/                           # conversations (tracked)
      council-caching-debate/
        thread.json                    #   metadata (gitignored)
        0001-king.md                   #   messages (tracked)
        0002-claude.md
        0003-codex.md
      kin-042-work/
        thread.json
        0001-king.md
        0002-peasant-kin-042.md
    sessions/                          # agent runtime state (gitignored)
      claude.json
      codex.json
      peasant-kin-042.json
    logs/                              # agent output (gitignored)
      peasant-kin-042/
        stdout.log
        stderr.log
    state.json                         # branch state (gitignored)
  backlog/tickets/                     # existing (tracked)
  archive/                             # existing
  worktrees/                           # existing (gitignored)
```

Two file types: `.md` is tracked, `.json`/`.log` is gitignored. No new gitignore rules needed.

- `agents/` is *who*, `tickets/` is *what*, `threads/` is *what they said*, `sessions/` is *what they're doing right now*.

### The Hand as Lead

The Hand is the King's primary coding agent — Claude Code, Cursor, etc. The King works inside the Hand's TUI. In the multi-agent system, the Hand acts as **team lead** for peasants, analogous to the "lead" in Claude Teams.

**What the Hand does as Lead:**
- Spawns peasants on ready tickets (`kd peasant start`)
- Monitors their progress (`kd peasant status`)
- Reads escalations and responds (`kd peasant read`, `kd peasant msg`)
- Reviews completed work and runs quality gates (`kd peasant review`)
- Uses `kd peasant status` to see what needs attention
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

`kd peasant status` is the Hand's main entry point for supervision — it shows active peasants, their status (working/blocked/done/dead), and elapsed time.

### Command Surface

**Council — the unified conversation interface:**

```bash
# Council (broadcast to all advisors)
kd council ask "Should we use Redis?"              # new thread, all members
kd council ask --async "Should we use Redis?"      # fire-and-forget (returns thread ID)
kd council ask --to codex "Elaborate on pooling"   # same thread, one member
kd council ask "Final recommendations?"            # same thread, all members
kd council ask --thread new "Different topic"      # explicit new thread

kd council show [thread-id]                        # show thread history
kd council watch [thread-id]                       # live stream the conversation
kd council list                                    # list threads
```

The current `kd council ask` / `kd council followup` / `kd council critique` collapse into one command. `ask` defaults to "continue current thread" if one exists.
- **Interactive mode (default):** Streams responses to stdout. The Hand sees the output.
- **Async mode (`--async`):** Returns the thread ID immediately. The King can then watch the debate in a separate terminal (`kd council watch <thread-id>`) to prevent the Hand from "taking over" the synthesis.

**Council inside the Hand's TUI:** Council queries take 60-120s (multiple agent subprocesses). When the King runs `kd council ask` as a local command inside Claude Code, long-running commands get backgrounded automatically — output goes to a capture file instead of displaying inline. The King never sees the responses without manually retrieving them.

The workaround today is two-step: `kd council ask` (backgrounds), then `kd council show` (instant, stays foreground, renders panels inline). This works but isn't obvious.

The better design is to make `kd council ask` async: dispatch agents in the background and return immediately ("Querying council-XXXX..."). Agents write responses to the thread as they finish. `kd council show --wait` polls until responses arrive and displays them. The first command is instant (never backgrounds), the second blocks but actively renders. This also means the King can fire off a question and check back later — more chat-room than RPC.

**Council permissions:** Council agents must run without elevated permissions (no `--dangerously-skip-permissions` or equivalent). Council is read-only — agents advise, they don't act. Skip-permissions flags should only be passed for peasant execution. Currently `build_command()` inserts them unconditionally.

**Peasant execution:**

```bash
kd peasant start KIN-042 [--agent claude]  # create worktree + launch agent
kd peasant status                           # table of active peasants
kd peasant logs KIN-042 [--follow]          # tail logs
kd peasant msg KIN-042 "Focus on tests"     # send directive
kd peasant read KIN-042                     # read escalations
kd peasant review KIN-042                   # review work + run quality gates
kd peasant stop KIN-042                     # stop the agent process
kd peasant sync KIN-042                     # pull parent branch changes into worktree
```

`kd peasant start` does what the current `kd peasant` does (worktree + branch) plus:
1. **Setup**: runs `uv sync` and `pre-commit install` in the worktree to ensure dependencies and hooks are ready.
2. Creates `sessions/peasant-KIN-042.json`
3. Creates a `kin-042-work` thread with members `[peasant-kin-042, king]`
4. Seeds the thread with a `ticket_start` message (ticket content, acceptance criteria, refs)
5. Launches the backend agent as a subprocess in the worktree
6. Captures stdout/stderr to log files (ensuring agent "thought" output is visible, not just harness logs)

**Status overview:**

```bash
kd status
# Shows: branch, design/breakdown status, tickets, active agents, unread messages
```

### How Peasants Actually Work

`kd peasant start` launches a **background process** that runs an autonomous loop. The peasant works until the ticket is done or it needs help.

The **harness** (`kd agent run`) is the loop:

```
while not done and not blocked:
    1. Build prompt (ticket + acceptance criteria + worklog + any new directives)
    2. Call backend CLI (claude --print --resume $SESSION_ID ...)
    3. Parse response
    4. Agent commits its own changes
    5. Append to worklog (decisions made, bugs hit, difficulties)
    6. Update session file (status, resume_id, last_activity)
    7. Write response as message to thread
    8. Check: done? blocked? new directives in thread?
```

The peasant runs tests (`pytest`) and linters (`ruff`) when it makes sense — the agent decides, like an engineer would. Not on every iteration.

**Harness quality gates must match review gates.** The harness DONE condition must validate the same things `kd peasant review` checks — currently pytest AND ruff. If the harness only runs pytest but review also runs ruff, the peasant will claim "done" with lint failures and get bounced by review. The harness should run both `pytest` and `ruff check` before accepting a DONE signal.

**Harness logging must include test output.** When tests or lint fail, the harness must log the actual failure output (which tests failed, error messages), not just "Tests failed, overriding DONE to CONTINUE." Without this, debugging from logs is impossible.

**Stop conditions:**
- **Done** — ticket acceptance criteria met, tests pass, and lint/formatting checks (`ruff`) pass. Status → `done`.
- **Blocked** — needs a decision, hit something unexpected, can't proceed. Status → `blocked`. Writes escalation to thread.
- **Stopped** — King/Hand sent `kd peasant stop`. Status → `stopped`.
- **Failed** — unrecoverable error. Status → `failed`.

**Commits:** The agent is prompted to commit as it works with descriptive messages. Pre-commit hooks run normally. This gives the Hand/King visibility into progress via `git log`.

**Worklog:** The ticket itself has a pre-formatted worklog section at the bottom. The peasant appends to it as it works — decisions made, bugs encountered, difficulties, test results. The worklog is part of the tracked ticket file, so it becomes part of the repo's history.

```markdown
## Worklog

- Implemented TokenManager.refresh() using existing OAuth client
- Decision: used exponential backoff for retry (3 attempts, 1s/2s/4s)
- Bug: refresh token was being URL-encoded twice, fixed in oauth_client.py
- Tests: 4/4 passing (refresh success, expired token, concurrent refresh, network error)
```

The peasant runs tests when it judges appropriate — not mechanically every turn. `kd peasant review` is for the Hand to do a final review after the peasant signals `done`.

### Quality Gates

On `kd peasant review KIN-042` (Hand reviews after peasant signals done):

1. Run `pytest` in the worktree (verify peasant's claim)
2. Run `ruff check`
3. Review the diff and worklog
4. Accept (merge ticket branch) or reject (send feedback, peasant resumes)

If the Hand rejects, the peasant gets a feedback message and status goes back to `working`. If the peasant process has exited, `kd peasant review --reject` **automatically restarts it** so it can address the feedback immediately.

## What We're NOT Building (v1)

- No daemon/server process
- No `kd watch` live dashboard (use `kd status` + `kd peasant status`)
- No `kd peasant manage` dashboard (use `kd peasant status` to see what needs attention)
- No tmux automation (launch agents in background; user can tmux manually)
- No autonomous agent-to-agent messaging (peasants talk to King/Hand, not to each other)
- No separate foreman agent (the Hand fills this role)
- No event ledger
- No channel abstraction
- No complex permission system

## Breakdown

### T1: Thread model
- Priority: 1
- Ticket: kin-56a5
- Depends on: none
- Description: Core data model for threads. Create/read/write thread directories under `.kd/branches/<branch>/threads/<thread-id>/`. Thread metadata in `thread.json` (members, pattern, created_at). Sequential message files (`0001-king.md`, `0002-claude.md`) with YAML frontmatter (from, to, timestamp, refs). Thread IDs are sanitized using the existing `normalize_branch_name()` function. Helpers: `create_thread()`, `add_message()`, `list_messages()`, `list_threads()`, `next_message_number()`.
- Acceptance:
  - [x] `create_thread(branch, thread_id, members, pattern)` creates directory + thread.json
  - [x] Thread IDs are normalized via `normalize_branch_name()` (same sanitization as branch directories)
  - [x] `add_message(branch, thread_id, from_, to, body, refs)` writes next sequential .md file
  - [x] `list_messages(branch, thread_id)` returns messages in order
  - [x] `list_threads(branch)` returns all thread IDs with metadata
  - [x] Messages use YAML frontmatter matching the design doc format
  - [x] Tests cover create, add, list, sequential numbering

### T2: Agent config model
- Priority: 1
- Ticket: kin-304a
- Depends on: none
- Description: Parse agent definition `.md` files from `.kd/agents/`. Markdown with YAML frontmatter (name, backend, cli, resume_flag). Replace hardcoded `ClaudeMember`/`CodexMember`/`CursorAgentMember` classes with a single config-driven `Agent` class that builds commands from the config. Keep the existing `CouncilMember.parse_response()` logic as backend-specific parsers. Create default agent files on `kd init`.
- Acceptance:
  - [x] `load_agent(name)` reads `.kd/agents/<name>.md` and returns config
  - [x] `list_agents()` returns all registered agents
  - [x] Agent config drives command building (replaces hardcoded CLI strings)
  - [x] Backend-specific response parsing preserved (claude JSON, codex JSONL, cursor JSON)
  - [x] `kd init` creates default agent files for claude, codex, cursor
  - [x] `kd doctor` checks agent CLIs based on config

### T3: Agent session state
- Priority: 1
- Ticket: kin-2d8e
- Depends on: none
- Description: Per-agent runtime state in `sessions/<agent>.json`. Each agent writes only its own file (no locking needed). Helpers to get/set agent status, resume_id, pid, ticket, thread, timestamps. Agent status enum: idle, working, blocked, done, failed, stopped. Branch-level `current_thread` stays in `state.json`. Migrate existing `.session` files (plain text resume IDs) to the new `.json` format on first access.
- Acceptance:
  - [ ] `get_agent_state(branch, agent_name)` reads `sessions/<agent>.json`
  - [ ] `set_agent_state(branch, agent_name, **fields)` writes `sessions/<agent>.json`
  - [ ] `list_active_agents(branch)` scans sessions/ for agents with status != idle
  - [ ] `get_current_thread(branch)` / `set_current_thread(branch, thread_id)` manage current thread pointer in state.json
  - [ ] Existing `.session` files migrated to `.json` on first read (read old format, write new format, remove old file)
  - [ ] Existing state.json fields preserved

### T4: Council refactor
- Priority: 2
- Ticket: kin-111b
- Depends on: T1, T2, T3
- Description: Rewire `kd council ask` to use threads + agent configs. Merge `ask`/`followup`/`critique` into unified `ask` with `--to` flag. `ask` defaults to continue current thread if one exists, or start new thread if not. `--thread new` forces a new thread. Add `--async` flag to return immediately. Add `kd council show` (static) and `kd council watch` (live tail). Remove old `followup` and `critique` commands. Store council resume tokens in per-agent session files. Keep parallel execution via ThreadPoolExecutor.
- Acceptance:
  - [ ] `kd council ask "prompt"` creates thread on first use, continues on subsequent
  - [ ] `kd council ask --async` returns thread ID immediately without waiting
  - [ ] `kd council ask --to codex "prompt"` sends to one member only
  - [ ] `kd council ask --thread new "prompt"` starts a fresh thread
  - [ ] All messages written to thread directory as sequential .md files
  - [ ] Resume tokens stored in `sessions/<agent>.json`, used on follow-up queries
  - [ ] `kd council show` displays thread history with Rich panels
  - [ ] `kd council watch` tails the thread message files live
  - [ ] `kd council list` shows all council threads
  - [ ] Old `followup` and `critique` commands removed

### T5: Peasant execution
- Priority: 2
- Ticket: kin-54d6
- Depends on: T1, T2, T3
- Description: Agent harness (`kd agent run`) that runs an autonomous loop: build prompt from ticket + worklog + directives, call backend, apply changes, commit, run tests, append to worklog, update session, write to thread. Loop continues until done (acceptance criteria met, tests pass), blocked (needs help), or stopped. `kd peasant start <ticket>` creates worktree + branch, creates session file, creates work thread, seeds with ticket_start message, launches harness as background process. `kd peasant status` shows table of active peasants. `kd peasant logs <ticket> [--follow]` tails subprocess logs. `kd peasant stop <ticket>` kills process. Ticket file has a pre-formatted worklog section that the peasant appends to as it works.
- Acceptance:
  - [x] `kd agent run --agent <name> --ticket <id> --worktree <path>` runs autonomous loop
  - [x] Loop: prompt → backend → agent commits → worklog → repeat
  - [x] Loop stops on: done (tests pass, criteria met), blocked (needs help), stopped, or failed
  - [x] Agent commits as it works with descriptive messages (pre-commit hooks run)
  - [x] Peasant appends decisions, bugs, difficulties to worklog section in ticket
  - [x] `kd peasant start KIN-042` creates worktree, session, thread, launches harness in background
  - [x] `kd peasant status` shows table: ticket, agent, status, elapsed, last activity
  - [x] `kd peasant logs KIN-042` shows stdout/stderr
  - [x] `kd peasant logs KIN-042 --follow` tails logs
  - [x] `kd peasant stop KIN-042` sends SIGTERM, updates status to `stopped`
  - [x] Peasant output written as messages to work thread
  - [x] Session file updated with pid, status, timestamps

### T6: Peasant messaging and supervision
- Priority: 3
- Ticket: kin-b369
- Depends on: T5
- Description: `kd peasant msg <ticket> "message"` writes a directive to the work thread (peasant picks it up on next loop iteration). If the harness has already exited (dead/done/stopped), the directive is written to the thread but never read — `kd peasant msg` should warn when the target peasant is not running. `kd peasant read <ticket>` shows recent messages from the peasant (escalations, status updates). `kd peasant review <ticket>` is the Hand's final review after peasant signals done — verify tests, review diff and worklog, accept or reject.
- Acceptance:
  - [ ] `kd peasant msg KIN-042 "focus on tests"` writes directive to thread, peasant picks up on next iteration
  - [ ] `kd peasant read KIN-042` shows peasant's messages (escalations, worklog updates)
  - [ ] `kd peasant review KIN-042` runs pytest + ruff, shows diff + worklog for Hand review
  - [ ] Hand can accept (ticket closed, branch ready to merge) or reject (feedback sent, peasant resumes)

## References

Prior design docs (archived to `docs/archive/`):

- `gpt-pro-design.md` — Protocol/runtime/UX layer separation, agent sessions with mailboxes, worker loop model
- `gpt-pro-v2.md` — Synthesized court runtime proposal, event ledger, quality gates, migration plan
- `message-passing-design.md` — Court unified agent model, channels/routing patterns, message-as-primitive
- `multi-agent-system-deep-dive.md` — Option analysis, CLI-first architecture, tmux guidance, permission profiles
