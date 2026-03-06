# Design: Long-Running Autonomous Workflows

## Goal

Make Kingdom capable of autonomously executing multi-ticket workstreams with minimal King intervention. Today, the King manually starts peasants, polls status, reviews work, accepts/rejects, and starts the next batch. This design introduces a **lord** — a supervisor agent that manages the full inner loop — and the supporting infrastructure to make that loop robust across long-running sessions.

## Context

### What exists today

Kingdom already has the pieces for parallel agent work:
- **Peasants** work tickets in isolated worktrees with a harness loop (iterate → council review → bounce/accept)
- **Council** reviews peasant work automatically, with a 3-bounce escalation to the King
- **Tickets** have deps, status, worklogs, `parent` field, and a `--ready` filter for unblocked work
- **Sessions** track peasant state (working, needs_king_review, etc.) with file locking
- **Watch** tails worklogs, git status, and agent logs in real-time
- **`kd peasant accept/reject`** already exist for resolving completed work
- **`kd tk list --json`**, **`kd tk show --json`**, **`kd tk current --json`** already exist

### What's missing

1. **No supervisor loop.** Starting peasants, reviewing finished work, and unblocking the next wave requires the King to manually run commands.

2. **No epic grouping.** The `parent` field exists but has no guardrails — no type validation, no close enforcement, no child listing.

3. **Worktrees are checkout-rooted.** Peasant worktrees resolve from the current checkout, breaking when the King works from a different long-lived worktree.

4. **Council threads vanish on archive.** Can't reference design decisions from previous branches.

5. **Watch is blind to council.** Shows "still working" while a peasant waits on council responses.

6. **`kd done` blocks on TTY prompts.** Interactive confirmation hangs non-interactive callers.

7. **`--ready` filter is too loose.** Doesn't exclude custom statuses like `blocked` — only excludes `in_review` and `closed`.

8. **Missing `--json` on agent-facing commands.** `kd peasant status`, `kd peasant show`, `kd council list`, `kd council status`, and `kd deps tree` lack machine-readable output. Agents currently parse rich tables, which is fragile.

## Architecture: The Lord Loop

The lord is an **LLM agent** that calls `kd` commands in a poll loop. It uses reasoning to review peasant work, resolve merge conflicts, and decide when to escalate. It is not a deterministic script — review judgment, conflict assessment, and escalation decisions require natural language understanding.

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
  │     5. Log cross-ticket progress to epic worklog (if epic)
  │     6. Sleep <interval> (default 5 minutes)
  │     │
  │     └── Exit when: all tickets closed, or max runtime, or King signal
  │
  └── kd lord status → show managed tickets, active peasants, progress
```

The lord is itself an agent session (like a peasant, but with the `lord-` prefix). It runs in the base checkout on the feature branch — no worktree needed since it only calls `kd` commands, never edits code directly.

### CLI-driven, not library-driven

The lord interacts with Kingdom through `kd` commands, not by importing Python internals:
- The lord prompt is instructions + the `kd` CLI reference
- Any agent backend (Claude, Codex, etc.) can be a lord
- Actions are observable via worklogs, threads, and session state
- No new Python orchestration layer needed

### Merge conflict resolution

When `kd peasant accept` merges a worktree branch back to the feature branch, later merges may conflict when multiple peasants work in parallel. The lord handles this the same way a human does:

1. Run `kd peasant accept <id>`
2. If the merge fails (exit code 1), go into the worktree and resolve the conflicts
3. Commit the resolution, then retry `kd peasant accept <id>`
4. If the conflicts are too complex (large semantic overlaps), escalate to the King
5. Log the resolution or escalation to the epic worklog

No changes to `kd peasant accept` needed — the existing error output already provides recovery steps.

### Epic worklog as the cross-ticket journal

When the lord manages an epic, the **epic ticket's worklog** is where cross-ticket information lives:
- Merge conflict resolutions
- Implementation decisions that span multiple tickets
- Progress summaries ("3/7 tickets closed, 2 in progress, blocked on X")
- Escalation notes for the King

Individual ticket worklogs stay ticket-scoped. The epic worklog is the lord's journal — the single place to read for the big-picture state of a workstream. This applies whether the lord, King, or Hand is driving.

### Review approach

The lord reads `kd peasant review <id>` output (markdown — council feedback, worklog, acceptance criteria) and decides whether to accept. It does NOT re-read all changed files or re-run tests — the peasant and council already did that. Review depth is configurable via `--review-depth` (summary | full).

### Lord stop mechanism

`kd lord stop` sets the lord's session status to `"stopping"`. The lord checks its own session status at the start of each cycle and exits cleanly when it sees `"stopping"`.

## Ticket Breakdown

### Layer 1: Foundation (parallelizable, no dependencies between them)

**ad3b — `kd tk status` (DONE)**
Set arbitrary ticket status strings. Already implemented.

**3e22 — Non-interactive `kd done`**
When stdin is not a TTY, skip the worktree-removal confirmation. Keep `--force` for skipping the open-ticket check separately.

**e872 — Watch shows council activity**
Wire `thread_response_status()` into the watch heartbeat. Show "Awaiting council response" with member status instead of "Still working."

**dfbb — Council threads survive archive**
Extend thread resolution to search archived branches as a fallback. Archived threads are read-only. Add `kd council list --all`.

**06a3 — `--json` output for agent-facing commands**
Add `--json` to: `kd peasant status` (must report effective status — "dead" not "working" for dead processes), `kd peasant show`, `kd council list`, `kd council status`, `kd deps tree`.

Note: `kd peasant review` stays markdown-only — its output is narrative council feedback that's easier to read and reason about as prose, not JSON.

**6207 — Fix `--ready` filter for custom statuses**
`--ready` should only include tickets with status `open` or `in_progress`, not "everything except in_review/closed." Custom statuses like `blocked` or `waiting` must be excluded.

### Layer 2: Hierarchical tickets

**d2b9 — Epic support**
Soft dependency for lord — lord can work flat ticket sets via `--all` without epics.

- `kd tk create -t epic "Feature name"` — type validation (task, bug, feature, epic)
- Child tickets get `parent: <epic-id>` in frontmatter
- `kd tk show <epic>` — child status rollup (3/5 closed)
- `kd tk list --parent <epic>` — list children
- `kd peasant start <epic>` — refuses (epics aren't atomic work)
- `kd tk close <epic>` — refuses if children are open
- Lord closes epic automatically when all children are done

### Layer 3: Multi-workspace

**39ac — Worktree path resolution from git common dir**
- Use `git rev-parse --git-common-dir` instead of checkout root
- Namespace: `.kd/worktrees/<branch>/<ticket-id>` to prevent collisions
- Ensure session state discoverability across long-lived worktrees

### Layer 4: Lord mode

**4178 — Lord mode**

A standalone `lord_loop()` (~150 lines) that reuses `session.py` for state management. Not shoehorned into the peasant harness — the harness is ~1100 lines coupled to code-editing workflows (worktree paths, diff stats, council review cycles) that the lord doesn't need.

**Commands:**
- `kd lord start [<epic-id>]` — launch supervisor (epic children or all branch tickets)
- `kd lord status` — managed tickets, active peasants, progress
- `kd lord stop` — signal graceful shutdown via session status
- `kd lord log` — lord's worklog and decisions

**Session:** `lord-<branch>` (one lord per branch), same schema as peasants.

**Configuration:**
- `--interval <seconds>` — poll interval (default 300s)
- `--review-depth summary|full` — how deeply to inspect peasant output
- `--max-peasants <n>` — concurrent peasant limit (default 3)
- `--max-runtime <hours>` — safety timeout (default 8h)

## Non-Goals

- Lord does NOT make design decisions — escalates to King
- Lord does NOT create or split tickets — works the set it was given
- Lord does NOT modify code directly — only through peasants
- No event-driven architecture — poll loop is sufficient
- No multi-lord coordination — one lord per branch
- No lord TUI in v1 — `kd lord status` + `kd peasant watch` suffice
- No cost tracking in v1
- No `--json` for `kd peasant review` — markdown output is better for agent comprehension

## Decisions

- **Agent lord, not deterministic**: Merge conflicts, review judgment, and escalation require LLM reasoning.
- **CLI-driven**: `kd` commands, not Python imports. Backend-agnostic, observable, testable.
- **Poll loop**: 5-minute sleep + poll. Interruptible via session status for `kd lord stop`.
- **Lightweight reviews**: Council does deep review. Lord checks AC + council verdicts.
- **Standalone lord loop**: Not the peasant harness. Simpler, purpose-built.
- **Epic is a soft dependency**: Lord works flat ticket sets (`--all`) without epics.
- **No re-scoping mid-run**: Escalate to King.
- **Failed peasant → mark blocked, continue**: Stop only when no runnable work remains.
- **Design phase optional**: `--require-design` flag (default off). Backlog sprints skip it.
- **Merge conflicts resolved by lord**: Same flow as a human — resolve in worktree, retry accept, escalate if too complex.
- **Epic worklog for cross-ticket state**: Lord logs progress, conflicts, and decisions to the epic ticket, not individual children.

## Dependency Order

```
3e22 (non-interactive done) ─┐
e872 (watch council)         │
dfbb (thread archive)        ├── Layer 1: foundation, parallelizable
06a3 (--json output)         │
6207 (--ready filter fix)    ┘
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

- Should `kd design` become optional in the standard workflow (only required for epics)? (Filed as backlog ticket 3732.)
