# Multi-Agent System Deep Dive for Kingdom

Date: 2026-02-07
Status: Draft proposal
Audience: Kingdom maintainers

## Executive Summary

Kingdom should keep a CLI-first architecture, but evolve from "one-shot subprocess calls" into a small runtime model with explicit state, events, and process supervision. tmux should be optional and used as an observability/interaction surface, not as the transport layer.

Recommended direction:

1. Keep files and subprocesses as the control plane.
2. Add a runtime event ledger and per-agent status files for live visibility.
3. Add a `kd watch` live dashboard first (no tmux dependency).
4. Add tmux as an adapter for attach/supervision, not correctness.
5. Avoid `tmux send-keys` as the core protocol.

This gives you a practical path from current code to parallel peasants and iterative council chat without introducing a brittle orchestrator.

## Inputs Reviewed

Local Kingdom docs and code:

- `docs/cli-skill-architecture.md`
- `docs/council-design.md`
- `docs/third_party/gastown.md`
- `docs/third_party/beads.md`
- `docs/third_party/ralph.md`
- `docs/third_party/openclaw.md`
- `docs/third_party/llm-council.md`
- `src/kingdom/cli.py`
- `src/kingdom/council/*.py`
- `src/kingdom/state.py`
- `tests/test_council.py`

External research (primary sources):

- Anthropic "Building Effective Agents" for "simple patterns first" guidance.
- Claude Code CLI reference for `--print`, `--output-format`, `--resume`, and streaming input format.
- OpenAI Codex CLI docs for `codex exec`, `--json`, and `exec resume`.
- tmux manual/wiki for `send-keys`, `wait-for`, and control mode protocol.
- Cursor "Scaling test-time compute" and changelog notes on planner/worker/judge and lock contention.
- Gastown README and docs for optional no-tmux mode and role decomposition.

## Current State (Reality Check)

What exists now:

1. Council one-shot queries in parallel (`kd council ask`) with per-member adapters and run bundles.
2. Session continuation storage for council members (`.session` files).
3. Follow-up and critique commands.
4. Ticket and worktree primitives (`kd peasant <ticket>` currently creates/removes worktree only).
5. Branch-centric durable markdown artifacts under `.kd/branches/<branch>/`.

What is missing for your stated multi-agent goals:

1. No long-running worker process model.
2. No live runtime status (heartbeats/state transitions) beyond static files.
3. No explicit queue semantics for "new instruction arrives while agent is busy".
4. No supervision surface for multiple active peasants.
5. No first-class "iterative council thread" workflow with routing semantics (targeted vs broadcast).

## Workflow-First Requirements

These workflows are the core design constraints.

### Workflow A: Iterative Design Discussion with Diverse Agents

Desired flow:

1. King asks all council members about a design issue.
2. King follows up with one member.
3. King asks all members again with refined scope.
4. King references previous responses while deciding.

Must-have capabilities:

1. Session continuity per member.
2. Thread-level storage of prompts and responses.
3. Fast targeted follow-ups (`--to codex`) and broadcast prompts.
4. No forced synthesis by Hand.

### Workflow B: Parallel Ticket Execution with Human Supervision

Desired flow:

1. King starts two to five peasants on unblocked tickets.
2. King sees who is active, blocked, idle, done, failed.
3. King can inspect logs and intervene.
4. King can stop/restart/reattach individual workers.

Must-have capabilities:

1. Per-worker lifecycle state.
2. Heartbeats.
3. Durable logs.
4. Isolation by worktree and ticket lock.

### Workflow C: Works in Headless and Remote Environments

Desired flow:

1. Same commands work in plain terminal, SSH, and CI.
2. tmux is optional, not mandatory.

Must-have capabilities:

1. Non-tmux runtime path.
2. Status and logs via files/CLI.
3. Graceful degradation when tmux is unavailable.

### Workflow D: Direct King Access Without Hand Mediation

Desired flow:

1. King can inspect council outputs and worker activity directly in terminal.
2. If desired, King can attach to agent session UI directly.

Must-have capabilities:

1. Direct `kd` views with no summarization.
2. Optional attach mode (tmux or direct subprocess logs).

## Option Analysis

### Option A: Pure CLI Snapshot Model

Summary:

- Keep one-shot subprocess calls and point-in-time status commands.

Pros:

1. Lowest complexity.
2. Maximum portability.

Cons:

1. Weak supervision for parallel workers.
2. Poor experience for long-running work and interrupts.

Fit:

- Good for MVP council ask.
- Insufficient for your peasant-parallel goal.

### Option B: tmux-Centric Runtime

Summary:

- Make tmux windows the primary execution and messaging mechanism.

Pros:

1. High visibility.
2. Direct attach UX.

Cons:

1. Hard dependency and lifecycle complexity.
2. Fragility if using `send-keys` for protocol-level correctness.
3. Harder CI/headless path.

Fit:

- High capability, high operational tax.

### Option C: Hybrid (Two Independent Paths)

Summary:

- Keep CLI for simple flows, add a separate tmux path for advanced usage.

Pros:

1. Flexible user experience.

Cons:

1. Risk of duplicated orchestration logic and drift.

Fit:

- Better than A or B alone, but only if core runtime is shared.

### Option D (Recommended): One Runtime, Multiple Surfaces

Summary:

- Shared control plane (files/events/processes).
- Multiple optional surfaces (CLI snapshot, live watch, tmux attach).

Pros:

1. Keeps simplicity in core.
2. Enables supervision and scale.
3. Avoids two separate orchestration implementations.

Cons:

1. Requires introducing a small runtime layer.

Fit:

- Best alignment with Kingdom goals and codebase philosophy.

## Architecture Proposal

## Design Principle 1: Separate Control Plane from UI Plane

Control plane:

- message envelopes
- event ledger
- process lifecycle
- locks and state transitions

UI plane:

- `kd council ask` / `kd council followup`
- `kd watch` live dashboard
- `kd attach` / tmux windows (optional)

Consequence:

- tmux can fail or be absent without breaking correctness.

## Design Principle 2: Explicit Runtime State

Introduce runtime state under current branch:

```
.kd/branches/<branch>/runtime/
  events.jsonl
  agents/
    <agent-id>/
      status.json
      heartbeat.json
      stdout.log
      stderr.log
  threads/
    <thread-id>/
      messages/
        <seq>-<from>-<to>.md
      index.json
  locks/
    ticket-<ticket-id>.lock
```

Notes:

1. This stays operational and gitignored by existing `.kd/.gitignore` patterns.
2. Tracked artifacts remain `design.md`, `breakdown.md`, `learnings.md`, `tickets/*.md`.

## Design Principle 3: Event-First Observability

Append-only `events.jsonl` records transitions and actions:

- `worker.started`
- `worker.heartbeat`
- `worker.blocked`
- `worker.completed`
- `worker.failed`
- `thread.message.sent`
- `thread.message.received`

Why:

1. Enables `kd watch` and later analytics without custom daemons.
2. Keeps postmortem/debug simple.

## Design Principle 4: Queue Semantics Must Be Explicit

Adopt simple queue modes inspired by OpenClaw:

1. `followup`: enqueue next instruction.
2. `collect`: merge rapid prompts into one next turn.
3. `interrupt`: request stop at next safe boundary.

Do not implement all at once. Start with `followup`, then add `collect`.

## Design Principle 5: Permissions Must Be Policy-Driven in Headless Mode

Headless execution still allows tool usage (read, write, bash). The difference is that permission decisions are policy-driven instead of interactive `Y/N` prompts.

Implications:

1. No interactive prompt can be satisfied in detached/background workers.
2. Council and peasants need explicit per-role policy presets.
3. If a prompt requires human approval and none is possible, the worker must transition to blocked state, not wait indefinitely.

Current Kingdom note:

1. Council subprocesses run with no stdin attached (`stdin=DEVNULL` in `src/kingdom/council/base.py`), so a TUI approval prompt cannot be answered there.

### Recommended Permission Profiles

| Role | Mode | Tool capability | Prompting behavior | Required outcome |
|---|---|---|---|---|
| Council | Detached/headless | Read-only preferred | Never interactive | Return/refuse/error quickly |
| Peasant | Detached/headless | Write + bash allowed by policy | Never interactive | Execute or `blocked: permission_required` |
| Hand | Attached interactive | Full (user-controlled) | Interactive allowed | Human can approve/deny |
| Peasant | Attached (`--attach`) | Full (user-controlled) | Interactive allowed | Human can approve/deny |

### Runtime Rule for Unattended Workers

If a detached peasant/council call hits a permission boundary:

1. Set `status = blocked`.
2. Set `blocked_reason = permission_required`.
3. Emit `worker.blocked` event with command context.
4. Keep logs and last error for operator intervention.

## Council Design Under This Model

### Keep Existing Commands, Add Thread Semantics

Current commands are usable but thread semantics are implicit. Add explicit thread model:

1. `kd council ask` creates thread + run bundle for one broadcast turn.
2. `kd council followup` appends targeted message to same thread.
3. Add `kd council thread start <name>` and `kd council thread send` for iterative flow.

### Suggested Thread Commands

```
kd council thread start design-oauth
kd council thread send design-oauth --to all "Prompt"
kd council thread send design-oauth --to codex "Follow-up"
kd council thread show design-oauth
kd council thread list
```

### Why This Helps

1. Keeps your direct King-to-council pattern.
2. Removes ambiguity around "what run am I following up on?"
3. Preserves one-shot UX for simple usage.

## Peasant Runtime Under This Model

### Worker Process Contract

A peasant run should be a real process, not only a worktree creation command.

Minimal worker loop responsibilities:

1. Read assigned ticket and acceptance criteria.
2. Execute coding-agent steps in worktree.
3. Emit heartbeats and status updates.
4. Emit blocked/failure reasons explicitly.
5. Run quality gates before completion.
6. Record work log and summary.

### Suggested Commands

```
kd peasant start <ticket-id> [--agent claude|codex|cursor] [--attach]
kd peasant status
kd peasant logs <ticket-id> [--follow]
kd peasant stop <ticket-id>
kd peasant resume <ticket-id>
```

### Locking and Isolation

1. One active worker per ticket lock file.
2. One worktree per ticket branch.
3. Reject duplicate starts unless `--force`.

## Observability Surfaces

### Surface 1: CLI Snapshot (Always Available)

- `kd peasant status`
- `kd council thread show`

### Surface 2: Rich Live Dashboard (No tmux Required)

Add `kd watch`:

1. Poll `runtime/events.jsonl` + status files.
2. Render live table of workers and council activity.
3. Works in plain terminal and CI logs.

This should be built before tmux integration.

### Surface 3: Optional tmux Attach

tmux integration should provide convenience:

- window management
- quick attach/switch
- visibility of full interactive CLIs

tmux should not be required for message transport correctness.

## tmux-Specific Guidance

1. Avoid `tmux send-keys` as the main protocol.
2. If tmux automation is needed, prefer control mode for structured output handling.
3. If `send-keys` is used at all, use it for best-effort nudge only.
4. Maintain no-tmux parity for all critical operations.

Reasoning:

- `send-keys` injects keystrokes into pane input and can collide with whatever state the program is in.
- tmux control mode exists specifically for machine interaction with structured `%begin/%end/%error` and async notifications.

## Simplicity vs Capability Tradeoff

Do not build a daemon mesh yet.

Avoid now:

1. Multi-level watchdog hierarchy.
2. Cross-repo routing.
3. Complex role taxonomies.
4. Rich web UI.

Build now:

1. One event ledger.
2. One worker process model.
3. One live dashboard command.
4. Optional tmux adapter.

This is enough to unlock your two key goals without becoming Gastown-scale complexity.

## Recommended Migration Plan

### Phase 0: Stabilize Contracts (1-2 days)

1. Define runtime event schema.
2. Define worker status schema.
3. Define council thread schema.

Acceptance criteria:

1. Schema docs exist and examples are committed.
2. Backwards compatibility path for existing council bundles is documented.

### Phase 1: Add Runtime Ledger + Watch (2-4 days)

1. Add event append utility.
2. Emit events from current council commands.
3. Implement `kd watch` live view.

Acceptance criteria:

1. Council commands populate runtime events.
2. `kd watch` shows progress in near-real-time.

### Phase 2: Real Peasant Execution (4-7 days)

1. Implement `kd peasant start/status/logs/stop` with detached process mode.
2. Add heartbeat + blocked/failed/done states.
3. Add ticket lock handling.

Acceptance criteria:

1. Two peasants can run in parallel on independent tickets.
2. Stuck process is visible as stale heartbeat.

### Phase 3: Council Thread UX (3-5 days)

1. Add explicit council thread commands.
2. Preserve existing `ask/followup` as convenience wrappers.

Acceptance criteria:

1. King can run multi-turn targeted and broadcast design discussions with clear thread identity.

### Phase 4: tmux Adapter (Optional, 3-6 days)

1. Add `kd attach` and `kd tmux up` wrappers.
2. Keep runtime identical with/without tmux.

Acceptance criteria:

1. Same worker/thread state visible and controllable in both modes.

## Risks and Mitigations

Risk: Runtime complexity drifts toward orchestrator bloat.

Mitigation:

1. Keep scope to branch-local workflows.
2. Reject features requiring daemon mesh until proven necessary.

Risk: Agent CLI flag drift breaks integrations.

Mitigation:

1. Keep adapter-level smoke checks in `kd doctor`.
2. Version adapter contracts and parse errors explicitly.

Risk: Worker hangs or waits for human input forever.

Mitigation:

1. Heartbeat timeout marks stale.
2. Emit `worker.blocked` state with reason.
3. Optional bailiff command can nudge or resume.

Risk: tmux path diverges from non-tmux behavior.

Mitigation:

1. tmux uses the same worker commands.
2. No separate execution logic inside tmux adapter.

## Concrete Product Decisions to Lock

1. tmux is optional.
2. Core runtime transport is files + subprocesses.
3. `send-keys` is never correctness-critical.
4. `kd watch` is first-class and ships before tmux automation.
5. Peasant state machine and heartbeat are mandatory for parallel execution.
6. Council thread identity becomes explicit.

## Open Questions (Narrow, Actionable)

1. Should peasant workers auto-commit during execution or only at completion checkpoints?
2. Should `kd peasant start` default to detached mode or attached mode?
3. Should council threads default to branch-scoped names or globally unique IDs?
4. Should `kd watch` be a single combined dashboard or split into `kd council watch` and `kd peasant watch`?

## Suggested Immediate Next Step

Implement Phase 1 before any tmux work. It gives immediate visibility and informs whether you truly need heavier session orchestration.

## External Sources

- Anthropic, Building Effective Agents: https://www.anthropic.com/engineering/building-effective-agents
- Claude Code CLI reference: https://docs.anthropic.com/en/docs/claude-code/cli-reference
- OpenAI Codex CLI docs: https://github.com/openai/codex/blob/main/docs/cli.md
- tmux manual (send-keys/control mode/wait-for): https://man7.org/linux/man-pages/man1/tmux.1.html
- tmux control mode wiki: https://github.com/tmux/tmux/wiki/Control-Mode
- Cursor, Scaling test-time compute: https://cursor.com/blog/scaling-agents
- Cursor changelog (planner/worker/judge): https://cursor.com/changelog/multi-agent-structured-output-and-seamless-refactoring
- Gastown README: https://github.com/steveyegge/gastown
