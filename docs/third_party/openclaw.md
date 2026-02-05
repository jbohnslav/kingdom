# OpenClaw: Analysis for Kingdom

Source: `third-party/openclaw/`

## Overview

OpenClaw is a **personal, single-user AI assistant** intended to run on your own
devices as an always-on service. Instead of living inside a single chat app, it
connects to many “channels” (WhatsApp/Telegram/Slack/Discord/Signal/iMessage,
etc.) and exposes a local **Gateway** control plane (WebSocket API) that other
clients can attach to (CLI, web UI, macOS app, mobile “nodes”).

At a high level:

- The **Gateway daemon** owns the long-lived integrations and message routing.
- An embedded **agent runtime** (derived from “pi-mono”) handles LLM calls, tool
  execution, and session behavior.
- A user-controlled **workspace directory** provides the agent’s durable
  working context via injected bootstrap files like `AGENTS.md`, `SOUL.md`,
  `TOOLS.md`, and user/profile files.
- The system is designed for “always-on” UX: streaming responses, presence/
  typing indicators, retries + idempotency, and message queueing/steering when
  new user input arrives mid-run.

What problem it solves: “I want an assistant that feels local, fast, and
persistent, and that I can talk to in the channels I already use, with device
capabilities (canvas/camera/screen/location) available as tools.”

Relevance to Kingdom: OpenClaw isn’t a “build software from tickets” system, but
it has mature patterns around (1) durable context and session storage, (2) tool
policy and safe retries, and (3) a typed evented control plane for multi-client
interaction. Those can inform Kingdom’s `.kd/` state model and long-running
worker ergonomics even if we keep Kingdom’s orchestration (Hand/Council/Peasant)
and repo-local workflow.

## Core Architecture

OpenClaw is a “daemon + control plane + agent runtime” system. The important
distinction is:

- The **Gateway** is the long-lived, stateful process that owns provider
  connections and all “messaging surfaces”.
- The **agent runtime** is invoked by the gateway to produce responses (and run
  tools), with continuity defined by the gateway’s session store + files on disk.

### Topology: Gateway, Clients, Nodes

- The Gateway exposes a single **WebSocket server** (default bind
  `127.0.0.1:18789`) used by:
  - operator/control clients (CLI, web UI, macOS app, automations)
  - “nodes” (macOS/iOS/Android/headless devices) that declare `role: node` and
    offer device capabilities (`canvas.*`, `camera.*`, `screen.record`,
    `location.get`).
- A separate **canvas host** (default port `18793`) serves agent-editable UI
  (HTML + “A2UI” state) for node displays.
- Invariants called out in their docs:
  - Exactly **one gateway per host** controls a WhatsApp session.
  - The gateway handshake is mandatory: the first WS frame must be `connect`,
    otherwise the socket is closed.

### Gateway Protocol: Typed Frames + Events

Protocol shape is intentionally small and uniform:

- **Frames**:
  - Request: `{type:"req", id, method, params}`
  - Response: `{type:"res", id, ok, payload|error}`
  - Event: `{type:"event", event, payload, seq?, stateVersion?}`
- Typical `agent` flow:
  1. client sends `req:connect`
  2. gateway responds with `hello-ok` + a “snapshot” (presence/health/etc)
  3. client sends `req:agent`
  4. gateway acks “accepted” with a `runId`, then streams `event:agent` updates,
     then sends a final response.
- **Idempotency**: side-effecting methods (notably `send` and `agent`) require an
  `idempotencyKey`; the gateway keeps a short-lived dedupe cache so clients can
  retry safely.
- **Events are not replayed**; clients are expected to refresh state if they
  detect gaps.

Typing + schema pipeline (worth noting because it keeps the gateway surface
coherent as it grows):

- **TypeBox schemas** are the source of truth for the WS protocol.
- JSON Schema is generated from TypeBox and used for runtime validation.
- Swift models are generated from the JSON Schema for the macOS client.
- The docs name these key locations:
  - `third-party/openclaw/src/gateway/protocol/schema.ts` (protocol schemas)
  - `third-party/openclaw/src/gateway/protocol/index.ts` (AJV validators)
  - `third-party/openclaw/src/gateway/server.ts` (handshake + method dispatch)
  - `third-party/openclaw/dist/protocol.schema.json` (generated JSON Schema)
  - `third-party/openclaw/apps/macos/Sources/OpenClawProtocol/GatewayModels.swift`
    (generated Swift models)

### Agent Runtime: Workspace-Backed Context + Sessions

OpenClaw’s agent runtime (derived from “pi-mono”) is file-centric:

- There is an **agent workspace directory** (`agents.defaults.workspace`) that
  acts as the agent’s default `cwd` and primary durable context store.
- On the first turn of a session, OpenClaw **injects** the contents of standard
  workspace files into the model context (skipping blanks; truncating large
  files with a marker). Key files include:
  - `AGENTS.md` (operating rules + “how to use memory”)
  - `SOUL.md` (persona/boundaries)
  - `TOOLS.md` (user tool/convention notes)
  - `IDENTITY.md`, `USER.md`
  - `BOOTSTRAP.md` (one-time first-run ritual, intended to be deleted after)
- “Memory” is plain Markdown in the workspace:
  - `memory/YYYY-MM-DD.md` daily logs
  - optional curated `MEMORY.md` (private session only)
  - OpenClaw can trigger a **pre-compaction “memory flush”** turn that nudges the
    model to write durable notes to disk before context compaction.

Sessions are explicitly persisted on the gateway host:

- Session store: `~/.openclaw/agents/<agentId>/sessions/sessions.json`
- Session transcripts: `~/.openclaw/agents/<agentId>/sessions/<SessionId>.jsonl`
- The store maps `sessionKey -> { sessionId, updatedAt, ... }` and is safe to
  delete entries from (they’re recreated on demand).

### Concurrency Control: Per-Session Queue + “Steering”

Because OpenClaw is always-on and can receive overlapping inbound messages, it
has two related mechanisms:

- A **lane-aware FIFO queue** that guarantees only one active run per session
  key (and caps global concurrency via `agents.defaults.maxConcurrent`).
- **Queue modes** that define what happens when new user input arrives during a
  run:
  - `collect` (default): debounce and coalesce into a single followup turn
  - `followup`: enqueue for the next turn
  - `steer`: inject into the active run and cancel remaining tool calls after
    the next tool boundary
  - other variants (`steer-backlog`, legacy `interrupt`)

This is a crisp, explicit answer to “what is a session allowed to do in parallel
with itself?” that’s often left fuzzy in agent systems.

### Model/Auth State: Profiles + Fallback

OpenClaw treats credentials as first-class state:

- Secrets are stored in `~/.openclaw/agents/<agentId>/agent/auth-profiles.json`
  (API keys + OAuth tokens).
- Failover strategy:
  1. rotate through auth profiles within a provider with cooldown/disable logic
  2. if profiles fail, fall back through configured model fallbacks
- The runtime “pins” an auth profile per session for cache friendliness and to
  avoid surprising rotation.

## Patterns Worth Adopting

### 1) “Workspace as the durable mind” (bootstrap files + Markdown memory)

OpenClaw is extremely explicit that the model “remembers” only what gets written
to disk:

- Durable context is a small, named set of workspace files (`AGENTS.md`,
  `TOOLS.md`, `SOUL.md`, `USER.md`, etc.) injected into every new session.
- Operational memory is plain Markdown (`memory/YYYY-MM-DD.md` plus optional
  curated `MEMORY.md`).

This cleanly separates:

- what is durable (files you can diff/backup)
- what is ephemeral (chat/session history)

Kingdom analogue: `.kd/runs/<feature>/` is already a natural workspace. The
OpenClaw pattern suggests making “learnings” and “operating constraints”
first-class, short, and always present for dev/test/review phases.

### 2) A compact, structured system prompt (fixed sections, inspectable)

OpenClaw’s prompt assembly is boring in the best way:

- fixed sections (tools, workspace, docs pointer, time, etc.)
- explicit note that skills/docs are available and how to load them
- inspectability via `/context list` / `/context detail`

Kingdom already has strong “phase framing”; this suggests we should keep
per-phase prompts small and consistent, with explicit “read these files if
needed” pointers instead of dumping large designs/breakdowns every time.

### 3) Typed control plane + runtime validation (TypeBox → JSON Schema → clients)

OpenClaw’s Gateway WS protocol is:

- uniform (req/res/event frames)
- validated at runtime (AJV)
- generated into clients (Swift) from the same schemas

Kingdom doesn’t need a network gateway, but the same idea applies to internal
interfaces that become “load-bearing”:

- `.kd/` state file formats
- ticket status transitions
- council request/response envelopes

A small schema for those artifacts reduces “stringly-typed drift” as the system
grows.

### 4) Idempotency-first side effects

OpenClaw requires `idempotencyKey` for side-effecting gateway methods so clients
can retry without duplicating sends or agent runs.

Kingdom analogue:

- if `kd` gains “remote-ish” operations (e.g. async workers, background runs, or
  run resumption), we should treat “start ticket run”, “mark ticket complete”,
  “write review comment”, etc. as idempotent operations with explicit keys.

### 5) Explicit concurrency semantics: per-session queue + steering

OpenClaw’s queue design answers two questions directly:

1. How many runs can exist per “conversation”? (one per session key)
2. What happens when new input arrives mid-run? (`collect` vs `followup` vs
   `steer`)

Kingdom analogue:

- per-ticket or per-peasant lane serialization (avoid two workers writing the
  same run/ticket state concurrently)
- a defined “interrupt semantics” story when the King sends new instructions
  mid-ticket (“cancel remaining tool calls after next boundary” is a nice,
  concrete definition)

### 6) Context-cost hygiene: tool-result pruning + compaction

OpenClaw uses two complementary techniques:

- pruning: transiently trims old tool results before a model call (especially
  TTL-aware for Anthropic prompt caching economics)
- compaction: persistently summarizes older chat into a stable summary in JSONL

Kingdom has a similar problem (long-running dev loops + large diffs + tool
output). Even if we don’t implement full “compaction”, copying the simpler
pruning idea could keep Peasant runs cheaper and more predictable.

### 7) “Profile pinning” + staged failover for reliability

OpenClaw treats credentials as state and has a staged strategy:

1. rotate auth profiles within a provider (cooldowns/disable on billing)
2. fall back across models/providers
3. pin a chosen profile per session for stability (unless user overrides)

Kingdom already conceptually wants “council diversity” and robustness. The
pragmatic takeaway is that reliability is mostly state + policy: treat model and
credentials as first-class, persisted run configuration, not incidental CLI
flags.

### 8) Minimal cross-session tools (list/history/send/spawn)

OpenClaw’s “session tools” are a small, hard-to-misuse surface for:

- listing sessions
- fetching history
- sending to another session
- spawning a sub-agent in an isolated session with an announce step

Kingdom analogue:

- a minimal, explicit “consult another worker” primitive that’s easy to reason
  about (instead of ad-hoc file reads or implicit context sharing)
  - especially useful for Council and “fresh agent per phase” loops

### 9) “Same as CI” local quality gates (and explicit security hygiene)

OpenClaw invests in boring, automatable checks:

- pre-commit hooks that run the same lint/format commands as CI
- secret scanning via `detect-secrets` with a committed baseline
- GitHub Actions linting (`actionlint`) and security auditing (`zizmor`)
- a “protocol output must be committed” check (`protocol:check`)
- test suites split into unit/e2e/live/docker, plus coverage thresholds

The Kingdom takeaway is less about copying tools and more about the discipline:
keep the “developer loop” and “CI loop” aligned so quality doesn’t depend on
heroics.

## Patterns to Skip

### Multi-channel “assistant product” surface area

OpenClaw’s core value is being an assistant you can use everywhere (WhatsApp,
Telegram, Discord, iMessage, etc.). That brings a lot of non-Kingdom complexity:

- connector implementations + provider-specific edge cases (rate limits, message
  formats, threading/topics, markdown quirks)
- message chunking/streaming/presence/typing indicators as product features

Kingdom should stay repo-local and keep its IO surfaces minimal (CLI + files).

### Device pairing + node capabilities

The node model (device identity, pairing approvals, node command surfaces, and
remote access support) is a separate product line. Kingdom does not need device
capabilities (canvas/camera/screen/location) for “ship code from tickets”.

### WebSocket gateway and client codegen (unless Kingdom becomes multi-client)

The typed WS protocol + Swift model generation is great engineering, but it only
pays off if Kingdom needs multiple independently developed clients talking to a
long-lived service. For MVP, Kingdom should avoid introducing a gateway.

The “schema discipline” is still worth copying internally (see above), but not
the networked architecture.

### OAuth/profile management as a first-class subsystem (for now)

OpenClaw’s OAuth/profile rotation is necessary because it’s a daily-driver
assistant that must run for long periods and survive account quirks. Kingdom can
start simpler (explicit API keys, explicit model selection) and only grow a
profile system if reliability demands it.

### Large configuration surface

OpenClaw has a broad, product-grade config surface (multiple channels, retry
policies, presence, routing, sandbox modes, etc.). Kingdom should aggressively
resist expanding config until real usage pressure appears.

## Why Not Just Use This?

OpenClaw and Kingdom optimize for different end-states:

- OpenClaw: “an always-on personal assistant” with rich IO surfaces, durable
  personal memory, device pairing, and a control-plane API.
- Kingdom: “ship repo changes reliably” via explicit phases (design → breakdown
  → tickets → dev/test/review/merge) and explicit artifacts in-repo (`.kd/`,
  `tk` tickets).

You could use OpenClaw *as the chat surface* to drive a Kingdom-like workflow,
but you would still need to build (or reintroduce) Kingdom’s core discipline:

- the ticket/dependency model
- multi-model Council review and synthesis
- reproducible test/review/merge gates tied to a git repo

So “replace Kingdom with OpenClaw” is mostly a category error. The more useful
approach is: copy OpenClaw’s reliability patterns (durable memory, explicit
queueing semantics, idempotent side effects, context hygiene) into Kingdom’s
repo-centric flow.

## Concrete Recommendations

1. Add a first-class “run workspace memory” file
   - Create `.kd/runs/<feature>/learnings.md` (or `MEMORY.md`) and make it part
     of the default context for dev/test/review prompts.
   - Keep it short and concrete (codebase conventions, decisions, gotchas).
   - Optionally mirror OpenClaw’s “daily log” idea with
     `.kd/runs/<feature>/memory/YYYY-MM-DD.md` for append-only scratch.

2. Define (and document) interrupt semantics for long-running work
   - Decide what happens when the King changes instructions mid-ticket.
   - OpenClaw’s `steer` definition is a good default: accept the new instruction,
     cancel any remaining tool calls after the next tool boundary, then continue
     from there.

3. Add concurrency locks around the artifacts that must never race
   - Minimal: a lock file per `run` and/or per `ticket` so two Peasants can’t
     write the same `.kd/runs/<feature>/…` state concurrently.
   - This is the Kingdom analogue of OpenClaw’s “one active run per session key”.

4. Make “side effects” idempotent by design
   - When a command creates or mutates state (start ticket run, mark complete,
     post review, write summary), assign a `runId`/`idempotencyKey` and persist it
     so retries/resumes don’t duplicate work.

5. Treat model choice as persisted run state, not just a flag
   - Record which model/provider each phase used (and any fallback taken) in a
     small `.kd/runs/<feature>/state.json`.
   - If Kingdom grows multiple key sources, consider OpenClaw-style “profile
     pinning” per run/ticket to keep behavior stable.

6. Add context-cost hygiene for long sessions (especially tool output)
   - Consider TTL-aware pruning for Anthropic prompt caching: aggressively trim
     old tool results before expensive calls, without rewriting history.
   - This can be implemented independently of full “compaction”.

7. Keep prompts compact by pointing at files instead of embedding them
   - Adopt OpenClaw’s “docs pointer + inspectability” posture:
     - prompts say “read `.../design.md` if needed” rather than pasting it all
     - provide a `kd context` command to show what was injected and how large it is

8. If Kingdom needs cross-agent collaboration, keep the surface minimal
   - OpenClaw’s `sessions_list/history/send/spawn` is a good template: a small,
     explicit “ask another agent” primitive beats ad-hoc file-based signaling.
