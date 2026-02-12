# Kingdom Multi-Agent Redesign (Synthesis)

Date: 2026-02-07
Status: Proposed
Audience: Kingdom maintainers

## Summary

This design keeps Kingdom simple while making it flexible enough for the workflows you want:

1. Human can talk to council directly (not only through the Hand).
2. Agents can talk to each other when explicitly allowed.
3. Peasants can work autonomously while the Hand or human advises.
4. tmux remains optional; correctness never depends on tmux.

The core decision is: **one file-backed protocol, one worker loop, many user surfaces**.

## Goals

1. Support iterative council conversations with targeted and broadcast follow-ups.
2. Support parallel peasant execution with clear supervision and escalation.
3. Keep headless/remote operation first-class.
4. Keep the design easy to explain and implement.

## Non-Goals (v1)

1. No daemon mesh or distributed orchestration.
2. No mandatory interactive TUI runtime.
3. No automatic global planner/foreman by default.
4. No protocol split between tmux and non-tmux modes.

## Design Principles

1. **Files are the transport**: messages, status, locks, events are all on disk.
2. **tmux is a viewport**: attach and intervene there if desired, but never rely on it for delivery.
3. **Roles are config, not code paths**: hand/advisor/peasant share the same primitives.
4. **Explicit queue and lock semantics**: no hidden behavior under concurrency.
5. **Simple by default, advanced by opt-in**: council independence by default, debate mode explicit.

## Core Model

### 1) Agent

Any participant that can receive and send messages.

Minimal tracked config (`.kd/court/agents/<name>.yaml`):

- `name`
- `role` (`hand`, `advisor`, `worker`, optionally `foreman` later)
- `runtime` (`subprocess`, `tmux`, `external`)
- `backend` (adapter key)
- `permission_profile`

### 2) Session

Durable runtime state for one agent on one branch.

Runtime path:

`.kd/branches/<branch>/runtime/agents/<agent-id>/`

Contains:

- `session.json` (backend resume token/state)
- `status.json`
- `heartbeat.json`
- `inbox/`, `processing/`, `outbox/`
- `logs/stdout.log`, `logs/stderr.log`

### 3) Message

Single communication primitive: markdown body + YAML frontmatter.

Required frontmatter:

- `id`
- `thread`
- `from`
- `to`
- `kind` (`prompt`, `reply`, `status`, `escalation`, `directive`, `control`)
- `expects` (`response`, `ack`, `none`)
- `created_at`

Optional:

- `reply_to`
- `refs` (file paths)
- `queue` (`followup` in v1)

### 4) Thread

Conversation identity across turns. Threads are how we keep iterative context clean and resumable.

### 5) Channel

Routing and policy for a set of members (`.kd/court/channels/<name>.yaml`).

Channel patterns:

1. `broadcast_collect`: one prompt to many, wait for replies.
2. `direct`: one-to-one.
3. `supervised_work`: worker + supervisor(s), with escalation semantics.
4. `debate`: explicit member-to-member visibility and messaging.

## Worker Runtime

All managed agents run the same loop:

`kd agent worker --agent <name> --branch <branch>`

Loop contract:

1. Claim next inbox message atomically (rename into `processing/`).
2. Execute backend with current session state.
3. Write output message(s) to outbox.
4. Update `status.json` and heartbeat.
5. Append structured event to `events.jsonl`.

Worker states:

- `idle`
- `starting`
- `working`
- `blocked`
- `done`
- `failed`
- `stopping`
- `stopped`

## Routing and Communication Policy

### Default behavior

1. Human can message any council member directly.
2. Human can broadcast to full council.
3. Council members reply to human (or hand), not each other.
4. Peasants can message supervisors (`king`, optional `hand`) for escalation.

### Opt-in behavior

1. Agent-to-agent communication is enabled only in channels with `pattern: debate` or explicit policy allow-list.
2. Peasant can request advisor input by sending to an allowed advisor channel (optional per ticket).

This keeps independent viewpoints as the default and prevents accidental groupthink.

## Direct Access Model (King and Hand)

The Hand is no longer a mandatory routing middleman. It is just another participant.

Practical consequence:

1. Human can run `kd` commands directly and read raw outputs.
2. Human can still ask the Hand to run `kd` commands when convenient.
3. Both flows hit the same thread/message/runtime state.

## Peasant Execution Model

Peasant = worker agent + ticket harness + isolated worktree.

Start flow:

1. Claim ticket lock: `runtime/locks/ticket-<id>.lock`.
2. Create/select ticket branch and worktree.
3. Start peasant worker.
4. Seed `ticket_start` message with ticket refs + acceptance criteria.

Supervision model:

1. Peasant posts status and escalations as messages.
2. Human or Hand replies with directives.
3. Optional advisor can be added for technical guidance (channel policy controlled).

## Observability Surfaces

1. **Snapshot CLI** (always works): `kd status`, `kd peasant status`, `kd council thread show`.
2. **Live CLI dashboard**: `kd watch` from `events.jsonl` + status files.
3. **Optional tmux attach**: full terminal access for unstructured intervention.

Implementation order is important: ship snapshot + watch first, tmux integration second.

## Minimal Command Surface

Generic:

- `kd send --to <agent|channel> --thread <id> "..." [--refs ...]`
- `kd read [--thread <id>] [--from <agent>]`
- `kd agent start <agent> [--bg|--tmux]`
- `kd agent stop <agent>`
- `kd agent logs <agent> [--follow]`
- `kd watch`

Council wrappers:

- `kd council ask "..." [--thread <id>]`
- `kd council followup --to <member> "..."`
- `kd council thread start <name>`
- `kd council thread send <thread> --to all|<member> "..."`

Peasant wrappers:

- `kd peasant start <ticket-id> [--agent <name>] [--bg|--tmux] [--plan]`
- `kd peasant msg <ticket-id> "..."`
- `kd peasant status`
- `kd peasant stop <ticket-id>`
- `kd peasant resume <ticket-id>`

## Concurrency and Safety Rules

1. Ticket claim is atomic. Duplicate starts fail unless forced.
2. Inbox claiming is atomic. One message is processed exactly once.
3. Detached workers never wait on interactive permission prompts.
4. Permission-boundary events set `state=blocked` with reason, never silent hang.
5. Stop means "at safe boundary" in v1, not forced mid-tool interruption.

## Hooks and Quality Gates (Minimal)

Hook points:

1. `WorkerIdle`
2. `TicketCompleted`

Exit semantics:

1. `0`: pass
2. `2`: reject completion and send feedback back to worker
3. non-zero otherwise: fail worker (configurable later)

This gives autonomy with guardrails without adding orchestration complexity.

## Runtime Layout

Tracked config:

- `.kd/court/agents/*.yaml`
- `.kd/court/channels/*.yaml`
- `.kd/court/policies/*.yaml`

Branch runtime (gitignored):

- `.kd/branches/<branch>/runtime/events.jsonl`
- `.kd/branches/<branch>/runtime/agents/<agent-id>/...`
- `.kd/branches/<branch>/runtime/threads/<thread-id>/...`
- `.kd/branches/<branch>/runtime/locks/*.lock`
- `.kd/branches/<branch>/runtime/worktrees/<ticket-id>/`

## Rollout Plan

### Phase 0: Lock contracts

1. Freeze message schema.
2. Freeze status/event schema.
3. Define lock file behavior.

### Phase 1: Runtime visibility first

1. Emit events from existing council commands.
2. Add `kd watch`.
3. Add explicit council thread identity.

### Phase 2: Real peasant workers

1. Implement worker loop and heartbeats.
2. Add ticket lock + isolated worktree + status/log commands.
3. Add blocked-state handling for permission boundaries.

### Phase 3: Controlled inter-agent comms

1. Add `debate` channel policy.
2. Add optional advisor-assisted peasant flow.
3. Keep default council independence unchanged.

### Phase 4: Optional tmux adapter

1. Start same worker loop in tmux windows.
2. Add attach/switch convenience commands.
3. Keep full parity with non-tmux mode.

## Acceptance Criteria

1. Human can run a full multi-turn council thread directly from CLI.
2. Human can target one member, then broadcast again in same thread.
3. Two peasants can run in parallel on different tickets with correct lock behavior.
4. Peasant escalation and supervisor directives work through messages.
5. Agent-to-agent messaging works only when enabled by channel policy.
6. `kd watch` shows live worker state and blocked reasons.
7. All core flows work without tmux.

## Final Design Decision

Kingdom should adopt a **single file-backed court runtime** with explicit threads, channels, sessions, locks, and events; provide direct human access and optional hand mediation on top; allow inter-agent communication by policy; and keep tmux as optional observability/intervention only.
