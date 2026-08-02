---
id: "2aed"
status: open
deps: [990d]
links: [029e, d3a5, 48dd, 329d, c759]
created: 2026-08-02T13:31:56Z
type: task
priority: 2
---
# Reorient Kingdom around session-scoped persistent tickets

## Problem

Kingdom's most valuable real-world behavior is making coding agents keep durable,
human-readable Markdown tickets and worklogs. The product currently gives too much
weight to workflows that are rarely used (especially design documents) and models
work as one active ticket per branch, even though the King commonly runs three to
five concurrent agent sessions in separate terminals on the same branch.

The global/recent "current ticket" is therefore often wrong, which also makes the
skill's automatic logging guidance unreliable. Peasant workers remain useful for
occasional high-autonomy execution, but their reviewer loop is token-expensive.
Epics are useful and have largely replaced the original design-doc workflow.

## Direction

- Make persistent Markdown tickets and worklogs the product center.
- Scope active ticket assignment to an agent/session/terminal, not a branch-global
  most-recent ticket.
- Preserve epics and occasional autonomous workers. Peasant work keeps council
  review as the safe default; the product should explain its cost and leave room
  for an explicit override only if later use proves one is needed.
- Retire or demote unused ceremony, especially the design-first happy path.
- Teach the skill that direct work, Kingdom workers, and native model subagents are
  complementary execution choices.
- Review recent multi-agent workflow developments for small additions that improve
  provenance, handoffs, recovery, and concurrent work without adding ceremony.

## Acceptance Criteria

- [ ] A skeptical product/code audit identifies what to keep, fix, demote, and remove.
- [ ] Active-ticket state is correctly isolated across concurrent terminal/agent sessions.
- [ ] Automatic ticket logging resolves the session's assigned ticket deterministically.
- [ ] The default skill workflow centers tickets and epics, with design docs optional.
- [ ] Peasant council review remains the default and its token/cycle costs are visible.
- [ ] The skill explicitly supports native subagents alongside direct and worker execution.
- [ ] Any new multi-agent features are justified by observed use, not framework ambition.

## Worklog

- 2026-08-02 — Skeptical audit confirmed the core current-ticket model remains
  branch-global. `kd tk current` scans every in-progress ticket in the resolved
  branch and returns the first priority/creation-sorted result. The v0.6 terminal
  context work only changes the Claude Stop hook's fallback target; it does not
  change `kd tk current`, assignments, status output, or the public lifecycle.

- 2026-08-02 — The terminal context adapter is not portable across current agent
  hosts. It keys known terminal environment variables and TTYs, but this Codex task
  exposes `CODEX_THREAD_ID` with no recognized terminal variable or TTY. The CLI
  also has no way to pass the Codex/Claude hook `session_id` into `kd tk start`.
  Result: a green hook test suite does not establish correct daily multi-session
  behavior.

- 2026-08-02 — Existing backlog epic `029e` already specifies first-class Hand
  identity, multiple concurrent hands, session-specific assignment, and status
  visibility. The skill's unconditional "create immediately; don't explore" rule
  caused this duplicate umbrella to be created before that ticket was discovered.
  Linked `029e`; the revamp should add a quick duplicate/context lookup before
  ticket creation.

- 2026-08-02 — Branch lifecycle is still the dominant data model: `kd start`
  refuses a second active session without `--force`, always scaffolds and advertises
  `design.md`, and tickets move among branch/backlog/archive directories. This is
  incompatible with several simultaneous outcomes on one working branch and makes
  ticket lookup/context code substantially more complex than the durable-Markdown
  use case requires.

- 2026-08-02 — Peasant council review is structurally mandatory whenever agents are
  configured: every DONE enters `run_council_review`, blocking findings can bounce
  the worker up to three times, and an empty council member list is defaulted back to
  all configured agents. There is no per-run review policy such as none, human, one
  cheap reviewer, or full council. Historical lord epics record the consequence:
  96 and 26 supervisor-agent cycles on two small epics, plus repeated council bounces.

- 2026-08-02 — Current Codex and Claude Code both provide native subagents with
  isolated contexts, model/tool policies, parallel orchestration, and inspectable
  agent threads. Codex now also exposes lifecycle hooks with stable session IDs and
  SubagentStart/SubagentStop events. Kingdom should own durable work identity and
  logging while delegating ordinary parallelism to the host; peasants/lords should
  remain an opt-in autonomy tier for worktree isolation, recovery, or unattended
  execution.

- 2026-08-02 — King corrected the audit: retain peasant-to-council review as the
  default, retain `tk pull` as the canonical backlog-to-work transition, and keep
  the TUI. Remove or deprecate arbitrary `tk move`; distinguish completed work
  from won't-do and other closure outcomes with explicit resolutions and reasons.

- 2026-08-02 — Dogfood corrections: active refactor tickets belong in the current
  branch, while backlog means "not right now." Pulled all five epics and their
  children into `codex/workflow-polish`. Also confirmed that minimal `tk create`
  stubs plus direct Markdown editing are a feature, not friction.

- 2026-08-02 — `kd tk close` already has good foundations: optional `--reason`,
  `--duplicate-of`, `closed_at`, backlog archiving, and open-child protection for
  epics. The missing piece is a typed resolution that distinguishes completed from
  won't-do/superseded/invalid outcomes and makes reasons queryable.

- 2026-08-02 — Added a paired dogfood experiment: implement Codex adapter `d023`
  with a native subagent and Claude adapter `92ca` with a peasant plus default
  council review, then compare cost, interventions, correctness, tests, and durable
  ticket quality in `648d`.

- 2026-08-02 — `kd tk list --parent c759` rendered a malformed narrow table with
  doubled borders, no useful title column, and a truncated location. Filed active
  child `beb1`. The dependency tree and cycle checker, by contrast, gave a clear
  validation of the cross-epic release path.

- 2026-08-02 — King questioned whether one dependency graph works across multiple
  epics. Code inspection found partial support rather than proof: lord readiness
  resolves dependencies across the branch and notices external status changes,
  but children are strictly direct-per-epic, no test runs two epics/lords, and a
  lord finishing does not close its epic ticket. Filed `4e2f`; replaced all
  epic-ID release dependencies with explicit leaf gates until this is proven.

## Roadmap

- `029e` — session-scoped ticket assignment and agent identity
- `d3a5` — host hooks, native subagents, and compaction durability
- `48dd` — explicit closure and a simpler backlog lifecycle
- `329d` — ticket-first skill, CLI, docs, and retained TUI
- `c759` — migration, real dogfooding, and release gates
