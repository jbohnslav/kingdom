---
from: claude
to: king
timestamp: 2026-02-16T20:03:20Z
---



Let me first look at the current project structure and existing ticket format so I can match the conventions.Good, I have the format conventions. Now let me write the summary ticket.Here's the standalone summary in ticket format:

---

```markdown
---
id: discussion-summary
status: draft
type: design
created: 2026-02-16T19:00:00Z
---

# Council-as-Supervisor: Action Ledger Design

## Context

During a council discussion comparing Kingdom to OpenClaw, the King observed that
his current workflow involves three concurrent panels: one for backlog capture, one
for code execution, and one for council consultation. This isn't a messaging problem
— it's a multiplexing problem caused by incomplete automation.

The council converged on a diagnosis: the three-panel workflow is a symptom of the
King doing supervisory work that the Council should handle. The fix isn't a richer
messaging/threading system (that path leads to reimplementing IRC). The fix is
**promoting the Council from advisory body to supervisor**.

## Core Insight

Today: King → Council (advice) → King (decides) → Peasant (executes)
Proposed: King → Council (supervises) → Peasant (executes)

The Council gains the ability to **propose typed actions** — filing tickets, spawning
peasants, checking status — using a machine-parseable syntax embedded in their
markdown responses. A policy layer classifies each action as auto-approved, requires
King approval, or forbidden. The King's interface shifts from "run three terminals"
to "review an inbox of proposed actions."

## The Action Block Syntax

Council members embed action proposals in fenced code blocks with an `action:` type:

    ```action:ticket_create
    title: "Increase default timeout for council queries"
    description: |
      Council queries occasionally time out under load.
      Default should be 5 minutes, not 2.
    priority: normal
    ```

YAML inside fenced markdown. Readable by humans, parseable by machines, diffable in git.

## Action Types (Phased Rollout)

### Phase 1 — Read-Only (ship first)
- `ticket_create` — file a backlog ticket
- `status_check` — query peasant/ticket status

### Phase 2 — Interactive
- `peasant_start` — spawn a peasant on a ticket
- `ticket_close` — close a completed ticket
- `ticket_reopen` — reopen a ticket

### Phase 3 — High-Trust
- `merge` — merge a branch
- `replan` — revise scope/design
- `scope_change` — modify ticket acceptance criteria

## Permission Model

Each action type has a policy classification:

| Action | Default Policy |
|---|---|
| `ticket_create` | auto |
| `status_check` | auto |
| `peasant_start` | requires_approval |
| `ticket_close` | requires_approval |
| `ticket_reopen` | requires_approval |
| `merge` | requires_approval |
| `replan` | requires_approval |
| `scope_change` | requires_approval |

Policy is configurable per-branch or globally in `.kd/config.yaml`.

## CLI Commands

### `kd council scan <thread-id>`
Parse a council thread and list pending (unexecuted) action blocks.

### `kd act [thread-id]`
Present pending actions interactively. For each action:
- Show the surrounding context (why the Council proposed it)
- Prompt for approval (auto-approved actions execute silently)
- Execute via existing `kd` commands (`kd tk create`, etc.)
- Mark the action as executed in the source markdown

### `kd supervise` (Phase 3)
Daemon mode. Watch for new council messages, auto-execute safe actions,
queue others for King approval. This is the "one panel" future.

## Execution Marking

After an action is executed, append a status line to the block:

    ```action:ticket_create
    title: "Increase default timeout"
    priority: normal
    # executed: 2026-02-16T19:05:00Z → ticket 4a3f
    ```

This prevents double-execution and provides an audit trail in the git history.

## Implementation Plan

### Step 1: Define the schema
- Strict YAML schema for each action type
- Start with `ticket_create` only (highest value, lowest risk)

### Step 2: Update council system prompts
- Teach the Council the action block syntax
- Instruct them to propose actions when confident, not just advise

### Step 3: Write the parser
- `kd council scan` — extract action blocks from thread markdown
- Handle edge cases: malformed YAML, unknown action types, already-executed blocks

### Step 4: Wire up `kd act`
- Interactive approval flow
- Dispatch to existing `kd` subcommands
- Mark executed in source file

### Step 5: Expand action types
- Add `peasant_start`, `ticket_close`, etc.
- Add policy configuration

### Step 6: `kd supervise`
- Background watcher
- Auto-execute per policy
- Notification for approval-required actions

## Design Principles

1. **Text as universal interface.** Actions are markdown. The ledger is the chat
   history. No new databases, no new wire protocols.
2. **Git-native.** Every action proposal, execution, and result is committed and
   diffable. The audit trail is `git log`.
3. **Incremental authority.** Start with one low-risk action type. Expand the
   policy as trust is earned through usage.
4. **No IRC.** No channels, no presence, no typing indicators, no real-time
   bidirectional messaging. The Council writes, the King reviews.
5. **Dissolve the panels.** The end state is one interactive session + an inbox.
   The three-panel workflow should feel obsolete, not "supported."

## What This Is Not

- Not a messaging system redesign (threads stay as-is)
- Not OpenClaw's gateway/channel architecture
- Not a new persistence layer (still `.kd/` markdown in git)
- Not a daemon (until Phase 3, and even then it's optional)

## Council Attribution

This design emerged from a full council discussion (claude, codex, cursor) with
the King on 2026-02-16. Key contributions:
- **Cursor:** "Context Manager" framing — the problem is context anxiety, not
  messaging. Proposed markdown action blocks as the protocol.
- **Codex:** Action ledger with typed records and policy-enforced execution.
  Pushed for strict schema and incremental rollout.
- **Claude:** Council-as-supervisor framing. Permission model (auto/approval/forbidden).
  Argued against premature infrastructure — finish peasant loop first.
- **King:** Identified the real goal — Council dispatches peasants, files tickets,
  monitors progress. The King reviews, not multiplexes.
```

---

Want me to write this to `docs/council-as-supervisor-design.md` or somewhere else in the repo?
