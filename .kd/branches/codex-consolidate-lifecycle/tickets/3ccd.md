---
id: "3ccd"
status: closed
deps: []
links: []
created: 2026-08-19T18:55:58Z
type: epic
priority: 2
closed_at: 2026-08-19T19:29:35Z
resolution: completed
close_reason: "Removed branch-finalization ceremony and consolidated workspace selection and readiness into start and status"
closed_context: codex:a775e0448cdb5a76
assignee: codex:a775e0448cdb5a76
---
# Consolidate workspace lifecycle commands

Remove branch-finalization ceremony from the ticket-first workflow. Workspace
readiness should be derived from ticket state, resource cleanup should stay with
the commands that own those resources, and selecting an existing workspace
should use the same idempotent entry point as creating one.

## Acceptance Criteria

- [x] `kd done` is removed instead of renamed, with readiness validation available through `kd status --check`.
- [x] `kd switch` is folded into `kd start <branch>` without changing per-context ticket ownership.
- [x] Ticket closure and peasant/context cleanup remain owned by their existing lifecycle commands.
- [x] Help, README, skill, release checks, and migration notes teach the smaller workflow.
- [x] Focused tests, manual CLI checks, Ruff, and the full suite pass.

## Children

- `e942` — read-only workspace readiness and removal of branch completion
- `9a13` — idempotent workspace selection through `kd start`
- `df56` — public workflow, smoke, release, and migration documentation

## Worklog

- [2026-08-19 15:00] [codex:a775e044] — Approved direction: remove done rather than rename it; use status --check for read-only readiness, start for workspace selection, and existing ticket/peasant/status cleanup owners. Delegated e942, 9a13, and df56 to separate native subagents for reviewed integration.
- [2026-08-19 15:29] [codex:a775e044] — All three reviewed children are closed. Integrated commits: fb7bf3b consolidates CLI lifecycle/state/tests; 73f1096 updates public workflow, smoke, release, and migration docs; b4aaf4f preserves established status-help wording after the full-suite review caught the regression. Final evidence: isolated smoke passed; manual root/start/status human+JSON and removed-command checks passed; full suite 2,179 passed, 38 skipped, 1 expected xfail; whole-tree Ruff check and format passed; uv-run pre-commit passed every hook; git diff check passed.
- [15:29] [codex:a775e0448cdb5a76] — Closed: Removed branch-finalization ceremony and consolidated workspace selection and readiness into start and status

## Lifecycle

- 2026-08-19T19:29:35Z [codex:a775e0448cdb5a76] — closed (completed): Removed branch-finalization ceremony and consolidated workspace selection and readiness into start and status
