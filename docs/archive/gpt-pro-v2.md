Kingdom Court Runtime

Date: 2026-02-07
Status: Synthesized proposal (v0.1)
Audience: Kingdom maintainers / implementers

This design merges the strongest parts of:
 • your original Kingdom workflow + council/peasants intent
 • the “CLI-first, event-ledger + watch dashboard” runtime proposal
 • the “Court” unification model (agents/channels/messages as one abstraction)
 • Claude Code Teams’ best mechanics (claiming, dependencies, quality gates, plan approval), without inheriting its “lead must synthesize” bias

The result is one coherent multi-agent architecture with one correctness model and multiple optional surfaces (CLI snapshot, live watch, tmux attach), so you don’t end up maintaining two orchestration paths.

⸻

1) Goals and constraints

Primary workflows

A. Iterative design discussion with diverse agents
 • Multi-turn threads
 • Targeted follow-ups + broadcast
 • Session continuity per member
 • King reads raw; no forced synthesis by the Hand

B. Parallel ticket execution with human supervision
 • 2–5+ peasants in parallel
 • Clear lifecycle states + heartbeats
 • Durable logs
 • Ability to intervene, stop/restart, reattach
 • Isolation via worktrees + per-ticket lock

C. Works headless / remote
 • No tmux required for correctness
 • Same commands work over SSH and in CI (with graceful degradation)

D. Direct King access
 • King can observe without the Hand editorializing
 • Optional “attach” into full interactive session when needed

Non-goals (for v1)
 • A daemon mesh, distributed routing, or cross-repo agent networks
 • “In-process multi-pane chat room” UI inside Kingdom (Rich Live is enough)
 • Perfect mid-turn interrupts (we’ll do “stop at safe boundary” first)

⸻

1) Key decisions to lock
 1. Files are the transport. All structured communication is file-backed messages + status + events.
 2. One runtime, multiple surfaces. tmux is a viewer/launcher/attach adapter, not a different protocol.
 3. Event-first observability. Append-only events.jsonl drives dashboards and debugging.
 4. Atomic claiming is mandatory. Tickets and inbox messages must be claimable with lock/rename semantics.
 5. Quality gates can block completion. Hooks can reject “done” and send feedback (Teams-style).
 6. Council independence is default. Advisors don’t talk to each other unless explicitly put in a “debate” channel.
 7. Headless permission boundaries block, not hang. Detached workers never wait for interactive approvals.

⸻

1) Architecture at a glance

                   ┌──────────── UI surfaces ─────────────┐
                   │  CLI: kd council / kd peasant / ...  │
                   │  Live: kd watch (Rich Live)          │
                   │  Optional: tmux attach/windows       │
                   └───────────────────┬──────────────────┘
                                       │
                                       ▼
              ┌──────────── Control plane (file protocol) ────────────┐
              │ messages (md+yml)   status/heartbeat   locks   events │
              └───────────────┬───────────────────────────┬──────────┘
                              │                           │
                              ▼                           ▼
                    Agent worker processes          Supervisor commands
                   (kd agent worker loop)         (start/stop/attach)

Everything “multi-agent” is just:
 • messages
 • worker loops
 • locks
 • events
 • surfaces (how you view/control)

⸻

1) Core abstractions

3.1 Agent (Court member)

Anything that can receive a message, do work, and send a reply.

Agent config (tracked, repo-level) describes what the agent is:
 • name (claude, codex, cursor, peasant-KIN-042)
 • role (hand, advisor, worker, optional foreman)
 • backend adapter (claude_code, codex_cli, cursor_agent, etc.)
 • runtime preference (subprocess, tmux, external)
 • permission profile (headless vs attached)

Important: roles are configuration, not code paths. The same message + worker mechanics apply; role just selects defaults.

3.2 Session

A session is the durable runtime state for one agent on one branch:
 • session resume tokens (per backend)
 • mailbox directories
 • logs
 • pid (if managed)
 • status + heartbeat

Sessions make “iterative” real: you can send follow-ups that use --resume or equivalent.

3.3 Message

The single communication primitive. Markdown body, YAML frontmatter for routing.

Minimal required frontmatter:
 • id (ULID recommended)
 • from
 • to (agent name or channel)
 • thread (optional but recommended for multi-turn)
 • kind (prompt, reply, status, escalation, control, etc.)
 • expects (response, ack, none)
 • refs (paths to relevant artifacts)

Messages are inspectable, diffable, portable, and survive crashes.

3.4 Channel / Thread

A channel is a named routing group plus a policy (“pattern”).
 • Thread: a conversation identity (multi-turn) for storage + session continuity.
 • Channel: a set of members + routing semantics.

In practice:
 • “Council” = a channel (broadcast-collect) + threads (design-oauth, etc.)
 • “Peasant work session” = a channel (supervised-work) + the ticket id as thread

3.5 Event ledger

Append-only events.jsonl records all meaningful transitions:
 • message sent/received
 • worker started/stopped
 • heartbeat
 • blocked reasons
 • task/ticket state changes
 • hook results

This is the backbone of kd watch.

3.6 Locks

Two locks matter in v1:
 • Ticket lock: one active worker per ticket (prevents duplicate peasants).
 • Inbox claim lock: one message processed once (prevents double-processing).

Implementation can be:
 • atomic file creation (O_EXCL)
 • atomic rename into processing/

⸻

1) File layout (tracked vs runtime)

Kingdom already has a strong split: .kd/ tracked except operational state. Keep that philosophy.

4.1 Repo-tracked (durable artifacts)

Per branch (existing):

.kd/branches/<branch>/
  design.md
  breakdown.md
  tickets/
  learnings.md (optional)
  council/                  # OPTIONAL: curated council transcripts
    <thread-id>/
      01..._king_to_all.md
      01..._codex_reply.md
      ...
  worklogs/                 # OPTIONAL: curated peasant completion reports
    KIN-042.md

Repo-level config (tracked):

.kd/court/
  agents/                   # agent definitions (portable, reviewable)
    claude.yaml
    codex.yaml
    cursor.yaml
    hand.yaml
  channels/                 # channel templates
    council.yaml
  policies/
    permissions.yaml
  hooks/
    TaskCompleted.d/
    TeammateIdle.d/

4.2 Branch runtime (gitignored, correctness state)

.kd/branches/<branch>/runtime/
  events.jsonl
  agents/
    <agent-id>/
      session.json
      status.json
      heartbeat.json
      pid
      inbox/
      processing/
      outbox/
      logs/
        stdout.log
        stderr.log
  threads/
    <thread-id>/
      messages/
      index.json             # optional convenience, not required
  locks/
    ticket-KIN-042.lock
    agent-claude.lock
  worktrees/
    KIN-042/                 # worktree dir (configurable)
    KIN-043/

Why this layout works
 • Branch-scoped runtime avoids cross-branch state collisions.
 • Tracked artifacts stay clean and meaningful.
 • Runtime is inspectable and debuggable without a daemon.

⸻

1) The worker process model

5.1 The invariant: “Everything goes through the worker loop”

Whether you run in tmux or detached subprocess, the agent process is:

kd agent worker --agent <name> --branch <branch> [--ticket KIN-042]

The worker loop:
 1. claims next inbox message (atomic)
 2. runs the backend adapter with resume state
 3. writes reply message to outbox
 4. updates status.json
 5. appends events to events.jsonl
 6. emits heartbeats

This is what prevents “two code paths”: tmux just launches the same worker in a window.

5.2 Worker lifecycle states

A minimal, useful state machine:
 • idle
 • starting
 • working
 • blocked
 • done
 • failed
 • stopping / stopped

status.json example:

{
  "agent": "peasant-KIN-042",
  "role": "worker",
  "state": "blocked",
  "since": "2026-02-07T15:44:12Z",
  "ticket": "KIN-042",
  "thread": "KIN-042",
  "last_message_id": "01J7XVKW...",
  "blocked_reason": "permission_required",
  "blocked_detail": "Backend requested approval to run `rm -rf ...`",
  "worktree": ".kd/branches/feature-auth/runtime/worktrees/KIN-042",
  "pid": 81342
}

Heartbeat file:

{ "ts": "2026-02-07T15:44:55Z", "state": "blocked" }

5.3 Safe “interrupt” semantics

Start with safe boundaries:
 • a worker checks for control/stop before starting a new message
 • kd peasant stop writes a control message + optionally sends SIGTERM

No mid-toolcall guarantees yet (matching Teams’ “shutdown can be slow” reality), but you get deterministic behavior.

⸻

1) Messaging protocol

6.1 Message format (markdown + YAML)

Example:

---
id: 01J7XVKW2Q6W7H8...
thread: design-oauth
from: king
to: council
created_at: 2026-02-07T15:30:12Z
kind: prompt
expects: responses
refs:

- .kd/branches/feature-auth/design.md
queue: followup

---

In design.md §3 we propose Redis. Argue for/against it. Suggest alternatives.

Replies include:
 • reply_to
 • from (agent)
 • to (king or channel)
 • kind: reply

6.2 Queue semantics (v1: followup)

Per agent inbox, the default is followup:
 • messages accumulate while agent is busy
 • processed in order (ULID timestamp order)

Roadmap:
 • collect (merge rapid-fire prompts into one next-turn)
 • interrupt (stop request)

6.3 Delivery model

Delivery is just file placement:
 • kd send writes message into recipient(s) inbox
 • worker claims and processes

For broadcast:
 • one message file can be copied to each member’s inbox
 • or you can generate per-recipient message IDs (often easier for correlation)

Events record:
 • message.sent
 • message.delivered
 • message.claimed
 • message.replied

⸻

1) Council design (advisors)

7.1 Council is “a channel + threads”
 • Channel template: council members = [claude, codex, cursor]
 • Pattern: broadcast-collect (default)

broadcast-collect semantics:
 • deliver prompt to all members
 • wait until all replies arrive (or timeout)
 • show raw responses in panels
 • store thread history

7.2 Commands (ergonomic layer, not new machinery)

Keep your current UX, but make thread identity explicit.

Convenience
 • kd council ask "..." → creates/uses a thread, sends to all, collects replies, prints.
 • kd council followup --to codex "..." → same thread, targeted.

Explicit thread control
 • kd council thread start <name> (or auto-ID)
 • kd council thread send <thread> --to all "..." [--refs ...]
 • kd council thread send <thread> --to codex "..."
 • kd council thread show <thread>
 • kd council thread list

7.3 Independence vs debate (important)

Default council mode preserves your core principle:
 • each advisor gets the same prompt and responds independently
 • no cross-agent messaging

Optional advanced pattern:
 • debate channel pattern: allow agents to see each other’s messages explicitly, when you want competing hypotheses to challenge one another (Teams’ “adversarial debugging” idea, but under your control).

7.4 Session continuity

Each council member session stores backend state:
 • session.json contains whatever the adapter needs (resume handle, conversation id, etc.)
 • the worker loop uses it automatically

This unlocks “iterative discussion” without inventing a chat room.

⸻

1) Peasants design (parallel ticket execution)

8.1 Peasant = worker agent + ticket harness + worktree

Starting a peasant:
 • claim ticket lock
 • create worktree + ticket branch
 • spawn worker process (tmux window or subprocess)
 • seed inbox with a ticket_start message containing ticket context

Recommended branch/worktree scheme:
 • feature branch: feature/auth
 • ticket branch: feature/auth/ticket-KIN-042
 • worktree: .kd/branches/feature-auth/runtime/worktrees/KIN-042/

This avoids “two worktrees on one branch” conflicts.

8.2 Ticket claim lock (correctness cornerstone)

kd peasant start KIN-042:
 • tries to create .kd/.../runtime/locks/ticket-KIN-042.lock
 • if lock exists:
 • refuse (default)
 • or --force to steal (with event recorded)

This is the Kingdom equivalent of Teams’ “file locking to prevent race conditions.”

8.3 Supervised-work channel pattern

Members: [peasant-KIN-042, king]
Thread: KIN-042

Expected message kinds:
 • peasant → king: status, escalation, blocked, completion_report
 • king → peasant: directive, approval, clarification, stop

This gives you structured supervision while keeping tmux as the unstructured escape hatch.

8.4 Plan approval mode (Teams-inspired, Kingdom-shaped)

For risky tickets, enable plan-gating:
 • Peasant must first send kind: plan with approach + tests
 • Worker remains in “plan-only” until it receives kind: approval
 • This can be per-ticket (plan_required: true) or per-command (kd peasant start --plan)

Crucially: the King approves, not an autonomous lead (unless you explicitly add a foreman later).

8.5 Quality gates + hooks (Teams’ strongest mechanic)

Add hook points:
 • TeammateIdle (worker about to go idle)
 • TaskCompleted / TicketCompleted (worker attempts to mark done)

Hook contract:
 • run scripts from .kd/court/hooks/TaskCompleted.d/*
 • exit code 0 → pass
 • exit code 2 → reject completion and produce feedback message to worker
 • other non-zero → mark worker failed (configurable)

Typical v1 gates:
 • uv run pytest
 • formatting/lint
 • “acceptance criteria checklist present”
 • “no forbidden files changed” (optional)

This is what turns “autonomous peasant” into “supervised and safe.”

8.6 Headless vs attached behavior
 • Detached/headless peasants: never interactive; on permission boundary → blocked
 • Attached peasants (tmux/interactive): King can intervene, approve, type, fix jams

⸻

1) Observability surfaces

9.1 Snapshot commands (always available)
 • kd status (branch overview: tickets + active agents + unread escalations)
 • kd peasant status
 • kd peasant logs KIN-042 --follow
 • kd council thread show <thread>

9.2 Live dashboard: kd watch (ships before tmux automation)

kd watch tails:
 • events.jsonl
 • agent status.json + heartbeats

Shows:
 • active agents, state, elapsed, last heartbeat age
 • blocked reasons
 • council threads awaiting replies
 • ticket locks / who holds them

This gives you 70% of “watch everyone live” without tmux.

9.3 Optional tmux adapter (visibility + intervention)

tmux is used for:
 • launching workers in windows/panes
 • attaching quickly
 • letting the King directly interact with a stuck agent

Hard rule: tmux is never correctness-critical.
No send-keys for protocol. If used at all, it’s a best-effort nudge (“check inbox”)—the protocol remains files.

⸻

1) Permissions and headless policy

Detached workers can’t answer interactive prompts, so permissions must be policy-driven.

Define permission profiles (repo config, overridable per user):
 • council_headless: read-only bias, no destructive ops
 • peasant_headless: allow write + bash within guardrails
 • interactive: everything allowed (King supervising)

Runtime rule:
If a detached worker hits a permission boundary:
 1. set state=blocked
 2. blocked_reason=permission_required
 3. emit worker.blocked event with details
 4. wait for a King directive (or fail fast in CI mode)

This prevents silent hangs.

⸻

1) Optional “Foreman” (Claude Teams lead, but Kingdom-compatible)

You can add a foreman later without changing the core model:
 • Foreman is an agent with role foreman
 • It operates in “delegate mode”: coordination-only tools (spawn, message, stop, update tasks)
 • It does not replace the King; it reduces manual routing

Where it helps:
 • managing 5–10 peasants
 • auto-assigning ready tickets
 • nudging stalled workers
 • collecting completion reports into a draft merge plan

Where it should not be used by default:
 • council synthesis (breaks your “King reads raw” principle)

Because the foreman still uses the same file protocol, it remains optional.

⸻

1) Minimal command surface (coherent and composable)

Generic primitives
 • kd agent start <agent> [--tmux|--bg]
 • kd agent stop <agent>
 • kd agent ps
 • kd agent logs <agent> [--follow]
 • kd send --to <agent|channel> --thread <id> "..." [--refs ...]
 • kd read [--from <agent>] [--thread <id>]

Council wrappers
 • kd council ask "..." [--thread <id>]
 • kd council followup --to <member> "..."
 • kd council thread start <name>
 • kd council thread send <thread> --to all|<member> "..."

Peasant wrappers
 • kd peasant start <ticket> [--agent claude|codex|cursor] [--tmux|--bg] [--plan]
 • kd peasant status
 • kd peasant logs <ticket> [--follow]
 • kd peasant stop <ticket>
 • kd peasant resume <ticket>

Observability
 • kd watch
 • kd status

⸻

1) Migration plan (practical, low-risk)

Phase 0: Contracts
 • Define schemas:
 • message frontmatter
 • status.json
 • events.jsonl entries
 • lock rules

Phase 1: Event ledger + watch
 • Emit events from existing kd council ask
 • Implement kd watch reading status/events
 • No peasants yet; immediate value

Phase 2: Real peasant execution (detached)
 • Implement worker loop + heartbeat + status
 • Ticket lock + worktree creation
 • Basic hooks for “TaskCompleted”

Phase 3: Council threads UX
 • Add explicit thread commands
 • Preserve ask/followup as wrappers

Phase 4: tmux adapter
 • kd agent start --tmux launches same worker loop
 • kd attach <agent> convenience
 • Keep parity with non-tmux

⸻

1) Why this synthesis is the “best of all takes”
 • From the Deep Dive: CLI-first, explicit runtime state, event ledger, kd watch before tmux, policy-driven headless permissions, avoid send-keys for correctness.
 • From the Court doc: unified agent model, channels/routing patterns, message-as-primitive, tmux as viewport + unstructured escape hatch, “roles are configs”.
 • From Claude Teams: task claiming via locks, dependency-aware tasks, plan approval mode, and hook-based quality gates that can block completion—without adopting “lead must synthesize”.
 • From the earlier protocol-first guidance: one worker loop + one file-backed bus so “hybrid” doesn’t mean two implementations.

⸻

The one-sentence architecture statement

Kingdom’s multi-agent system is a file-backed Court runtime with durable sessions, atomic locks, and an event ledger; agents are driven by a single worker loop, observed via kd watch, and optionally attached via tmux—so correctness never depends on tmux, and both council iteration and parallel peasants work under the same protocol.

If you want the next step to be actionable: I’d recommend you lock the schemas (message/status/event) and the ticket lock / inbox claim algorithm next, because once those are stable, everything else (watch UI, tmux adapter, council threads, peasants) becomes straightforward layering.
