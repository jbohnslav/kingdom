# Design: Long-Running Autonomous Workflows

## Goal

Make Kingdom capable of autonomously executing multi-ticket workstreams with minimal King intervention. Today, the King manually starts peasants, polls status, reviews work, accepts/rejects, and starts the next batch. This design introduces a **lord** — a supervisor agent that manages the full inner loop — and the supporting infrastructure to make that loop robust across long-running sessions.

## Context

### What exists today

Kingdom already has the pieces for parallel agent work:
- **Peasants** work tickets in isolated worktrees with a harness loop (iterate → council review → bounce/accept)
- **Council** reviews peasant work automatically, with a 3-bounce escalation to the King
- **Tickets** have deps, status, worklogs, and a `--ready` filter for unblocked work
- **Sessions** track peasant state (working, needs_king_review, etc.) with file locking
- **Watch** tails worklogs, git status, and agent logs in real-time
- **`kd peasant accept/reject`** already exist for resolving completed work
- **`parent` field** already exists on tickets for parent/child relationships

### What's missing

The King is still the scheduler. The gap between "peasant finishes" and "next peasant starts" is a human polling loop. Specifically:

1. **No supervisor loop.** Starting peasants, reviewing finished work, and unblocking the next wave requires the King to manually run commands. A lord agent closes this loop.

2. **No epic grouping.** A lord needs to know which tickets belong to a workstream. Today tickets are flat — no parent/child hierarchy with enforcement (the `parent` field exists but has no guardrails).

3. **Worktrees are checkout-rooted.** Peasant worktrees resolve from the current checkout, breaking when the King works from a different long-lived worktree in the same repo.

4. **Council threads vanish on archive.** A lord (or King) can't reference design decisions from a previous branch's council discussions.

5. **Watch is blind to council.** When a peasant dispatches a council query, watch says "still working" instead of showing the council is thinking.

6. **`kd done` blocks on TTY prompts.** A lord calling `kd done` would hang on the worktree-removal confirmation.

7. **`--ready` filter doesn't exclude custom statuses.** With arbitrary statuses (via `kd tk status`), a `blocked` ticket still appears as "ready." The lord needs a reliable way to find startable tickets.

8. **No `--json` on key commands.** The lord needs machine-readable output from `kd peasant status` and `kd peasant review`. Currently these only output rich tables.

## Architecture: The Lord Loop

The lord is an **agent** (not a deterministic script). It uses LLM reasoning to handle ambiguity — reviewing work quality, judging whether merge conflicts are resolvable, deciding when to escalate. It runs as a CLI-driven agent that calls `kd` commands.

```
kd lord start [<epic-id> | --all]
  │
  ├── Resolve ticket set (epic children or all branch tickets)
  ├── Loop:
  │     1. kd tk list --ready --json → find startable tickets
  │     2. For each ready ticket: kd peasant start <id>
  │     3. kd peasant status --json → check for completed peasants
  │     4. For each needs_king_review:
  │     │     kd peasant review <id> → read work + council feedback (markdown)
  │     │     Decide: accept or reject (with reason)
  │     │     kd peasant accept <id> / kd peasant reject <id> "reason"
  │     │     If merge conflict: resolve in worktree, retry (escalate if too complex)
  │     5. kd tk log <epic-id> "status update" (if epic)
  │     6. Sleep <interval> (default 5 minutes)
  │     │
  │     └── Exit when: all tickets closed, or max runtime, or King signal
  │
  └── kd lord status → show managed tickets, active peasants, progress
```

The lord is itself an agent session (like a peasant, but with the `lord-` prefix). It runs in the base checkout (no worktree needed — it only calls `kd` commands, never edits code directly).

### Key design choice: Agent, not deterministic

The lord is an LLM agent, not a state machine. This is intentional:
- **Merge conflicts**: when accepting peasant work, the lord merges the worktree branch back to the feature branch. If there are conflicts, the lord can assess whether they're trivial (auto-resolve) or complex enough to escalate to the King.
- **Review judgment**: the lord reads council feedback and acceptance criteria, then decides whether to accept. This requires natural language understanding, not pattern matching.
- **Unexpected situations**: a peasant might produce work that technically passes but misses the point. The lord can catch this.
- **Escalation decisions**: knowing when to stop and ask the King requires judgment.

### Key design choice: CLI-driven, not library-driven

The lord interacts with Kingdom through `kd` commands, not by importing Python internals. This means:
- The lord prompt is a set of instructions + the `kd` CLI reference
- Any agent backend (Claude, Codex, etc.) can be a lord
- The lord's actions are observable in the same way peasant actions are (worklogs, threads, session state)
- We don't need a new Python orchestration layer

### Merge conflict resolution

When the lord runs `kd peasant accept`, the peasant's worktree branch merges back to the feature branch. With multiple peasants working in parallel, later merges may conflict.

The lord handles this the same way a human does:
1. Run `kd peasant accept <id>`
2. If the merge fails (exit code 1), go into the worktree and resolve the conflicts manually
3. Commit the resolution, then retry `kd peasant accept <id>`
4. If the conflicts are too complex (large semantic overlaps), escalate to the King
5. Log the resolution or escalation in the worklog

No changes to `kd peasant accept`'s behavior needed — the existing error output already tells you the recovery steps.

**CWD requirement:** The lord must run on the feature branch. Since it runs in the base checkout and is launched via `kd lord start` (which validates the current branch), this is guaranteed at startup. The lord should not switch branches during its run.

### Review depth

The lord's review of peasant work is lightweight by default:
- Read the worklog and council feedback via `kd peasant review`
- Check if acceptance criteria are met (from ticket markdown)
- Check if council approved or had blocking concerns
- Accept if clean, reject with specific feedback if not

The lord does NOT re-read all changed files or re-run tests (the peasant and council already did that). Configurable via `--review-depth` (summary | full).

## Ticket Breakdown

### Layer 1: Foundation (parallelizable, no dependencies between them)

**3e22 — Non-interactive `kd done`**
Make `kd done` safe for non-interactive callers. When stdin is not a TTY, skip the worktree-removal confirmation (equivalent to `--force` for the confirm only, NOT for the open-ticket check). This unblocks the lord and any scripted usage.

**ad3b — `kd tk status` (DONE)**
Already implemented. Allows setting arbitrary ticket status strings.

**e872 — Watch shows council activity**
When the peasant watch detects `.stream-*.jsonl` files in the thread directory (indicating an active council query), display "Awaiting council response" instead of "Still working." `thread_response_status()` in `thread.py` already does this detection — wire it into the watch heartbeat.

**dfbb — Council threads survive archive**
When resolving a thread ID, search archived branches too (not just active ones). Threads in archived branches are read-only (can view, cannot append). Add `kd council list --all` to show threads across archived branches.

**NEW: `--json` output for lord-critical commands**
Add `--json` flag to `kd peasant status` and `kd peasant review`. The lord needs machine-readable output to parse peasant state reliably — it should not be parsing rich tables.

**NEW: Fix `--ready` filter for custom statuses**
The `--ready` filter currently only excludes `in_review` and `closed`. With arbitrary statuses (via `kd tk status`), a `blocked` ticket appears as "ready." Fix: `--ready` should only include tickets with status `open` or `in_progress` (explicitly startable statuses), not "everything except in_review/closed."

### Layer 2: Hierarchical tickets (soft dependency for lord — lord can work without epics)

**d2b9 — Epic support**
Add `type=epic` to the ticket system. Epics are tickets with children. Key behaviors:
- `kd tk create -t epic "Feature name"` creates an epic
- Child tickets get `parent: <epic-id>` in frontmatter
- `kd tk show <epic>` shows child status rollup (3/5 closed)
- `kd tk list --parent <epic>` lists children
- `kd peasant start <epic>` refuses (epics aren't atomic work)
- `kd tk close <epic>` refuses if children are open
- Type validation: task, bug, feature, epic (reject unknown types)
- When lord finishes all children, it closes the epic automatically

This gives the lord a natural unit of delegation: "manage this epic." But the lord can also work on flat ticket sets via `--all`.

### Layer 3: Multi-workspace

**39ac — Worktree path resolution from git common dir**
Peasant worktrees currently resolve from the checkout root. Switch to `git rev-parse --git-common-dir` so peasants launched from any long-lived worktree share the same worktree namespace.

Key changes:
- Worktree path: use git common dir, not checkout root
- Namespace: `.kd/worktrees/<branch>/<ticket-id>` (branch prefix prevents collisions)
- Session state: already branch-scoped, but ensure discoverability across worktrees
- Runtime state (logs, streams): kept in branch dir (already shared via git)

### Layer 4: Lord mode

**4178 — Lord mode**
The culmination. A separate `lord_loop()` (not shoehorned into the peasant harness) that reuses session management from `session.py`.

**Commands:**
- `kd lord start [<epic-id>]` — launch supervisor on an epic's children (or all branch tickets if no epic specified)
- `kd lord status` — show lord activity, managed tickets, active peasants, progress
- `kd lord stop` — signal lord to stop after current cycle (sets session status to `"stopping"`; lord checks its own status each cycle and exits cleanly)
- `kd lord log` — show lord's worklog/decisions

**Lord session:**
- Session name: `lord-<branch>` (one lord per branch)
- Session state: same schema as peasants (status, pid, last_activity, etc.)
- Work thread: `lord-<branch>/` for lord's own reasoning and decisions

**Lord agent prompt structure:**
```
You are a lord — a supervisor agent managing peasant workers.

Your job:
1. Start peasants on ready tickets
2. Monitor their progress
3. Review and accept/reject completed work
4. Resolve merge conflicts when merging peasant work back
5. Log progress and decisions

Available commands: [kd CLI reference subset]
Current state: [ticket list with statuses, active peasants, recent worklogs]

Rules:
- Only accept work that meets acceptance criteria
- Reject with specific, actionable feedback
- Log every decision to the worklog
- When all tickets are closed, close the epic (if applicable) and stop
- If stuck or uncertain, stop and escalate (don't guess on design decisions)
- Merge conflicts: resolve simple ones, escalate complex ones to the King
```

**Implementation: standalone lord loop, not peasant harness.**
The peasant harness (`harness.py`, ~1100 lines) is heavily coupled to code-editing workflows — worktree paths, diff stats, council review cycles. The lord doesn't edit code. A simpler `lord_loop()` function (~150 lines) that uses `session.py` directly and runs its own poll cycle.

**Configuration:**
- `--interval <seconds>` — poll interval (default 300 = 5 min)
- `--review-depth summary|full` — how deeply to inspect peasant output
- `--max-peasants <n>` — concurrent peasant limit (default 3)
- `--max-runtime <hours>` — safety timeout (default 8h)

## Design Doc Scope Change

The design phase (`kd design`) may only be needed for epics and large features, not every branch. Backlog sprints with well-scoped tickets can skip straight to execution. Consider making `kd design approve` optional — only required when `kd lord start` is given an epic, or when the King explicitly wants a design review.

## Non-Goals

- Lord does NOT make design decisions — it escalates to the King
- Lord does NOT create tickets — it works the set it was given
- Lord does NOT modify code directly — only through peasants
- No event-driven/webhook architecture — poll loop is sufficient and simpler
- No multi-lord coordination — one lord per branch
- No automatic epic detection or ticket decomposition by the lord
- No new storage model — lord uses existing session/thread/ticket infrastructure
- No lord TUI in v1 — `kd lord status` + `kd peasant watch` suffice
- No cost tracking in v1 — defer to backlog

## Decisions

- **Agent lord, not deterministic**: The lord is an LLM agent. Merge conflict resolution, review judgment, and escalation decisions require reasoning, not pattern matching. King's call — "absolutely a thousand percent no determinism."
- **CLI-driven, not library-driven**: The lord calls `kd` commands rather than importing Python internals. Backend-agnostic, observable, testable.
- **Poll loop, not event-driven**: Sleep + poll is dramatically simpler than file watchers or IPC. 5-minute intervals are fine — peasant work takes 10-30 minutes per ticket. Sleep must be interruptible for responsive `kd lord stop`.
- **Lord reviews are lightweight**: The council already does deep review. The lord checks AC completion and council verdicts, not code quality.
- **Separate lord loop, not peasant harness**: The peasant harness is too coupled to code-editing. A standalone `lord_loop()` reusing session management is cleaner.
- **One lord per branch**: No multi-lord coordination needed. More parallelism = more peasants.
- **Epic is a soft dependency for lord**: Lord can work on flat ticket sets (`--all`). Epic scoping is a refinement, not a prerequisite.
- **No re-scoping mid-run**: Lord doesn't create or split tickets. Escalate to King.
- **Failed peasant (3 bounces) → mark blocked, move on**: Don't stop the whole lord. Stop only when no runnable work remains.
- **Design-approved optional**: `--require-design` flag (default off). Backlog sprints don't need it.
- **Lord resolves merge conflicts**: Small/mechanical = auto-resolve. Large/semantic = escalate to King.

## Dependency Order

```
3e22 (non-interactive done) ─┐
e872 (watch council)         │
dfbb (thread archive)        ├── Layer 1: foundation, parallelizable
NEW  (--json output)         │
NEW  (--ready filter fix)    ┘
         │
         v (soft — lord works without epics)
d2b9 (epic support)         ── Layer 2: hierarchical tickets
         │
         v
39ac (multi-workspace)       ── Layer 3: worktree resolution
         │
         v
4178 (lord mode)             ── Layer 4: lord agent
```

## Open Questions

- ~~Should the lord be able to re-scope work mid-run?~~ No. Escalate to King.
- ~~Should `kd lord start` require a design-approved branch?~~ Optional via `--require-design`.
- ~~What's the right escalation when a peasant fails 3 times?~~ Mark blocked, continue. Stop when no runnable work remains.
- ~~Should the lord have a dedicated TUI?~~ Not in v1.
- Should `kd design` become optional in the standard workflow (only required for epics)?
