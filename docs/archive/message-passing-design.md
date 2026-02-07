# Kingdom: Multi-Agent Design Document

## Overview

Kingdom is a Python CLI toolkit (`kd`) that structures software development into phases: design, breakdown, develop, and merge. It's built around git branches as the organizing principle — `kd start` creates a `.kd/branches/<branch>/` directory with `design.md`, `breakdown.md`, and `tickets/`. You iterate on the design, break it into dependency-ordered tickets, work through them, and `kd done` archives everything. The `.kd/` directory is tracked in git (except operational state like JSON, logs, and sessions), so design decisions, breakdowns, and work logs become part of the repo's history.

This document describes the multi-agent communication and execution architecture that sits underneath Kingdom's workflow.

## Core Metaphor

Kingdom uses a feudal metaphor that maps directly to real roles:

- **The King** — the human developer. Makes decisions, sets direction, intervenes when things go wrong.
- **The Hand** — the King's primary coding agent (Claude Code, Cursor, etc.). The King works inside the Hand's TUI. The Hand executes `kd` commands on the King's behalf.
- **Advisors** — agents the King consults for perspective. They don't write code; they give opinions, critique designs, and surface blind spots. The "Council" is a group of advisors convened together.
- **Peasants** — worker agents that execute tickets autonomously in isolated git worktrees. They do the work, report status, and escalate when stuck.

These roles aren't separate systems. They're all **agents** — the same abstraction, with different roles and communication patterns.

## The Court: A Unified Multi-Agent System

The court is Kingdom's agent registry and message routing layer. Every agent — hand, advisor, peasant — is a court member. The court doesn't interpret messages. It delivers them and tracks who's alive.

### Agents

An agent is anything that can receive messages, do work, and send messages back. Each agent has:

- A **name** (unique identifier, e.g. `claude`, `codex`, `peasant-KIN-042`)
- A **role** (`hand`, `advisor`, `worker`)
- A **runtime** (`tmux`, `subprocess`, `external`)
- An **inbox** and **outbox** on disk

```yaml
# .kd/court/agents/claude.yaml
name: claude
role: advisor
runtime: tmux
cli: claude --print
resume_flag: --resume
session_dir: .kd/court/sessions/claude/
```

```yaml
# .kd/court/agents/peasant-KIN-042.yaml
name: peasant-KIN-042
role: worker
runtime: tmux
worktree: .worktrees/KIN-042/
ticket: KIN-042
cli: claude
session_dir: .kd/court/sessions/peasant-KIN-042/
```

```yaml
# .kd/court/agents/hand.yaml
name: hand
role: hand
runtime: external   # Kingdom doesn't manage the Hand's process
```

The Hand is special: its runtime is `external` because the King is already sitting inside it. Kingdom doesn't start or stop the Hand. But the Hand still has an inbox, and messages addressed to it show up when the King runs `kd read` or `kd status`.

### Messages

A message is a markdown file with YAML frontmatter for routing. Messages are the single communication primitive. Everything — council questions, peasant escalations, King directives, status updates — is a message.

```yaml
---
id: 01J7XVKW...
from: king
to: council              # channel name, agent name, or "broadcast"
channel: council-2025-02-07-001
timestamp: 2025-02-07T14:32:00Z
expects: response        # response | ack | none
refs:
  - .kd/branches/feature-auth/design.md
  - .kd/court/messages/01J7XVKA....md
---

What's the right caching strategy here? The design calls for Redis
but I'm wondering if we're overcomplicating this. See design.md §3.
```

Messages live in `.kd/court/messages/` as individual files, named by ULID for natural sort order. Channels and agents don't store messages — they reference them.

### Channels

A channel defines a communication pattern between a set of agents. It's a lightweight grouping with routing semantics.

```yaml
# .kd/court/channels/council/channel.yaml
name: council
pattern: broadcast-collect
members: [claude, codex, cursor]
```

```yaml
# .kd/court/channels/KIN-042/channel.yaml
name: KIN-042
pattern: supervised-work
members: [peasant-KIN-042, king]
escalation_to: king
```

#### Routing Patterns

| Pattern | Behavior | Typical use |
|---|---|---|
| `broadcast-collect` | Message goes to all members. Wait for all responses before surfacing. | Council asks |
| `direct` | 1:1 message. Wait for response. | King ↔ specific advisor |
| `supervised-work` | Worker posts status and escalations. Supervisor sends directives. | Peasant execution |
| `fire-and-forget` | Send, don't wait. | Notifications, FYIs |

Channels are cheap to create. An ad-hoc conversation between the King and one advisor is a channel. A peasant's work session is a channel. The council is a channel. You can create a channel with two peasants and an advisor to coordinate a tricky set of related tickets — it's the same primitive.

### File Layout

```
.kd/court/
  agents/
    hand.yaml
    claude.yaml
    codex.yaml
    cursor.yaml
    peasant-KIN-042.yaml
  channels/
    council/
      channel.yaml
    KIN-042/
      channel.yaml
  sessions/
    claude/
      ...                   # session continuity state for resume
    peasant-KIN-042/
      ...
  messages/
    01J7XVKA....md
    01J7XVKW....md
    ...
```

## Runtimes: How Agents Run

Agents need a process to run in. Kingdom supports three runtimes:

### `tmux` — Interactive Terminal Sessions

The default for any agent running interactively. Kingdom creates a tmux window in a shared session (`kd-kingdom`), one window per agent. The agent's CLI runs inside that window.

```
tmux session: kd-kingdom
┌──────────────────────────────────────────────┐
│ Windows:                                     │
│  0: hand (external — user's Claude Code)     │
│  1: council-claude                           │
│  2: council-codex                            │
│  3: council-cursor                           │
│  4: peasant-KIN-042 (working: oauth token)   │
│  5: peasant-KIN-043 (working: oauth ui)      │
└──────────────────────────────────────────────┘
```

Tmux serves two purposes:

1. **Visibility.** The King can switch to any window and see exactly what an agent is doing — its full TUI, tool calls, output, errors.
2. **Unstructured intervention.** When an agent hits an operational jam — a permissions error, a hanging test, a credentials prompt — the King switches to that pane, types directly into the terminal, fixes the problem, and leaves. The agent doesn't even need to know the King was there.

**Tmux is never a communication channel.** Kingdom never uses `tmux send-keys` to pass messages. All structured communication goes through message files. Tmux is where you watch; files are how they talk.

### `subprocess` — Headless Execution

For CI, remote servers, or environments without tmux. The agent runs as a managed subprocess. Logs go to files. Interactive prompts cause failures (which is fine — headless agents should be sandboxed enough to avoid them).

```bash
kd peasant start KIN-042 --headless
```

### `external` — Unmanaged

For the Hand. Kingdom doesn't start, stop, or manage the process. The agent exists outside Kingdom's lifecycle. It participates in the messaging system by reading and writing files when prompted.

## The Council: A Special Case of the Court

The council is not a separate system. It's a channel with `broadcast-collect` routing and a set of advisor agents. `kd council` commands are convenience wrappers around the court's general messaging.

### One-Shot Council Queries

For quick questions where you want all perspectives at once.

```bash
kd council ask "Is Redis overkill for our caching needs?"
```

This creates a message, sends it to the `council` channel, waits for all members to respond, and displays the collected responses. Mechanically, it spawns each advisor as a subprocess (or in tmux if a session is active), passes the prompt with any context refs, and collects the responses.

### Persistent Council Sessions

For conversational, multi-turn design discussions where the King wants to drill into individual perspectives and cross-pollinate ideas.

```bash
kd council open --context .kd/branches/feature-auth/design.md
```

This starts a council session: spins up tmux windows for each advisor (if not already running), loads context, and sets the council channel as the active session. From here, the King uses conversational commands:

```bash
kd say "What do you think about the Redis caching approach in §3?"
# → broadcast to all council members, wait for responses

kd say @claude "Elaborate on dropping manual invalidation."
# → DM to claude only

kd say --forward <msg-id> "Claude proposed this. Disagreements?"
# → forward a previous message to the full council

kd read
# → show unread messages, formatted in Rich panels

kd council close
# → end the session, archive the conversation
```

### UX Inside the Hand's TUI

The King is always inside the Hand's TUI (Claude Code, Cursor, etc.). Council interaction happens through `kd` commands that the Hand runs. The flow feels like a chat room even though it's CLI commands under the hood:

```
King (to Hand): let's get the council's take on caching

  Hand runs: kd council open --context design.md
  > 📢 Council session started: council-2025-02-07-001
  > Members: claude, codex, cursor
  > Context: design.md

King: ask them about the Redis approach

  Hand runs: kd say "What do you think about Redis for caching in §3?"
  > 📤 Sent to council (3 members)
  > 📩 codex responded (12s)
  > 📩 claude responded (18s)
  > 📩 cursor responded (24s)

  Hand runs: kd read
  > ┌─────────────────────────────────────────┐
  > │ 💬 codex                                │
  > │ Redis is overkill. In-process LRU cache │
  > │ covers this at your scale.              │
  > ├─────────────────────────────────────────┤
  > │ 💬 claude                                │
  > │ Keep Redis but simplify. Single cache,  │
  > │ TTL-based expiry, drop manual           │
  > │ invalidation entirely.                  │
  > ├─────────────────────────────────────────┤
  > │ 💬 cursor                                │
  > │ Use read-through caching. Don't cache   │
  > │ on write, cache on read with lazy       │
  > │ population.                             │
  > └─────────────────────────────────────────┘

King: interesting — ask claude to go deeper on the invalidation point

  Hand runs: kd say @claude "What does the simplified Redis approach
  look like concretely? Show me the cache flow."
  > 📤 Sent to claude (DM)
  > 📩 claude responded (15s)

  Hand runs: kd read
  > ┌─────────────────────────────────────────┐
  > │ 💬 claude (DM)                           │
  > │ Simple flow:                            │
  > │ 1. All keys get 5min TTL               │
  > │ 2. Read: cache → miss → DB → cache     │
  > │ 3. Write: DB, then delete cache key    │
  > └─────────────────────────────────────────┘

King: share that with the group, see if anyone disagrees

  Hand runs: kd say --forward <msg-id> "Claude proposed this. Thoughts?"
  > 📤 Forwarded to council
```

The Hand is the messenger, not the interpreter. It translates the King's intent into `kd` commands and runs them. The King sees the raw council output directly in the terminal. This preserves the core design principle: the King reads advisor responses without the Hand filtering or summarizing.

## Peasants: Parallel Ticket Execution

Peasants are worker agents that execute tickets autonomously. Each peasant works in an isolated git worktree on a single ticket.

### Starting a Peasant

```bash
kd peasant start KIN-042
```

This:
1. Creates a git worktree at `.worktrees/KIN-042/`
2. Registers a new agent (`peasant-KIN-042`, role: worker, runtime: tmux)
3. Creates a supervised-work channel for `[peasant-KIN-042, king]`
4. Opens a tmux window for the peasant
5. Launches the agent with the ticket context (description, acceptance criteria, dependencies, relevant code)
6. Starts the file-based supervision loop

### Structured Supervision

Peasants communicate through the court's messaging system, same as everyone else. The `supervised-work` channel pattern defines the expected interaction:

**Peasant → King:**
- Status updates (working, blocked, needs review, done)
- Escalations (design decisions, ambiguous requirements, unexpected problems)
- Completion reports

**King → Peasant:**
- Directives (guidance, corrections, clarifications)
- Approvals (for escalated decisions)

```bash
# King checks on all peasants
kd status
> 📬 1 unread escalation from peasant-KIN-042
>
> Active peasants:
>  KIN-042  oauth token refresh   ⚠️ escalation    12m
>  KIN-043  oauth UI components   🔨 working        8m
>  KIN-044  user settings page    ✅ done            2m

# King reads the escalation
kd read @peasant-KIN-042
> ┌────────────────────────────────────────────────┐
> │ ⚠️ peasant-KIN-042 (escalation)                │
> │ Ticket says "use existing auth module" but the │
> │ auth module doesn't support refresh tokens.    │
> │ Should I extend the auth module or write a     │
> │ standalone refresh handler?                    │
> └────────────────────────────────────────────────┘

# King sends a directive
kd say @peasant-KIN-042 "Extend the auth module. Add a refresh()
method to the existing TokenManager class."
```

### Unstructured Intervention

When a peasant hits an operational jam — a test hanging, a permissions error, a prompt waiting for input — the King switches to its tmux window and takes over directly.

```
# King notices peasant-KIN-043 has been "working" for 20 minutes
# with no status update. Switches to its tmux pane:
Ctrl-b 5

# Sees: pytest is hanging because port 5432 is already bound
# Types directly into the peasant's terminal:
kill -9 $(lsof -t -i:5432)

# Switches back to the Hand's pane:
Ctrl-b 0
```

The peasant doesn't need to know the King intervened. The blocking operation resolved, and the peasant continues its work.

### Headless Mode

For CI or automated pipelines, peasants run as subprocesses without tmux. Interactive jams cause failures rather than blocks. The supervision protocol still works — files are still written — but there's no escape hatch for unstructured intervention.

```bash
kd peasant start KIN-042 --headless
```

## Ticket System

The ticket system predates and is independent of the court. It defines *what work needs to be done*. The court defines *who does it and how they communicate*.

Each ticket is a markdown file with YAML frontmatter:

```yaml
---
id: KIN-042
status: in-progress
deps: [KIN-039, KIN-041]
priority: high
type: feature
assignee: peasant-KIN-042   # optional — links to a court agent
---

## OAuth Token Refresh

Implement automatic token refresh for OAuth sessions. When a token
expires, refresh it transparently without interrupting the user's flow.

### Acceptance Criteria

- TokenManager.refresh() obtains a new token using the refresh token
- Expired tokens are detected before API calls, not after 401s
- Refresh failures surface a clear error to the calling code
- Tests cover: successful refresh, expired refresh token, concurrent refresh
```

Tickets live in `.kd/branches/<branch>/tickets/` (branch-scoped) or `.kd/backlog/` (global). They have explicit dependency graphs — `deps` lists ticket IDs that must complete first. `kd ticket ready` surfaces tickets whose dependencies are all resolved.

When a peasant is assigned a ticket, the ticket's `assignee` field is set and the ticket becomes the peasant's work context. The peasant's supervised-work channel is named after the ticket ID.

## Design Principles

### Files Are the Communication Layer

All structured communication between agents goes through message files on disk. Never through terminal I/O, never through `tmux send-keys`, never through shared memory or sockets.

Files are inspectable (`cat`), diffable (`git diff`), persistent (they survive crashes), and portable (they work in any environment). Any tool that can read a file can participate in the court.

### Tmux Is a Viewport, Not a Transport

Tmux provides multiplexed terminal access so the King can observe and intervene with any agent. It is never used for message passing. If tmux isn't available, everything still works — you just can't watch agents live or intervene in their terminals.

### The King Reads Directly

Council responses and peasant escalations are presented to the King as-is. The Hand runs the `kd` commands and sees the output, but doesn't filter, summarize, or editorialize. The whole point of multiple agents is getting perspectives outside your primary agent's viewpoint. If the Hand mediates everything, that value is lost.

### Roles Are Configurations, Not Code Paths

Advisor, worker, and hand are roles assigned to agents via YAML. The communication primitives (messages, channels, routing patterns) are the same for all agents. The council isn't a separate system from peasant supervision — they're both channels with different routing patterns over the same message infrastructure.

### Structured Supervision, Unstructured Escape Hatch

The normal mode of agent coordination is structured: messages, status updates, escalations, directives. But when structure fails — an agent is stuck in a way it can't articulate, a process is hanging, something unexpected happened — the King drops into the tmux pane and handles it directly. The system is designed so that both modes coexist without conflict.
