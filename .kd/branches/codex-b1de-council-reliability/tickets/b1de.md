---
id: "b1de"
status: open
deps: []
links: []
created: 2026-08-19T21:46:02Z
type: epic
priority: 2
---
# Make Council reliable across sessions and repository states

Council operations should remain predictable when no workspace is active, when
agent backends are installed but unusable, when a review target is dirty, and
when chat messages arrive faster than a member can process them. Reliability and
recovery come before adding more Council backends or higher-level features.

## Dogfooding Objective

This is explicitly a post-1.0.0 Kingdom dogfooding epic. All workflow actions
must exercise the working-tree CLI through `uv run kd`, and the epic should test
the new ticket-first lifecycle end to end: branch setup, child-ticket execution,
durable worklogs, worker/review handoffs where appropriate, readiness checks,
and closure. Any workflow friction or unclear output discovered while doing the
Council work must be captured immediately as a concrete backlog ticket rather
than worked around silently.

## Acceptance Criteria

- [ ] Council list and ask commands handle missing active context without tracebacks or ambiguous fallback.
- [ ] Council review handles dirty repositories safely and gives an exact recovery path when it cannot proceed.
- [ ] Council chat queues messages without losing, overwriting, or silently reordering them.
- [ ] Doctor distinguishes an installed agent CLI from runtime, authentication, and configuration failures.
- [ ] Repository-configured Council backends remain consistent across primary and linked worktrees, including environments that intentionally use Cursor instead of Codex.
- [ ] Provider model and capability checks follow account-visible CLI behavior without putting Kingdom on a hardcoded model-name treadmill.
- [ ] Human errors and machine-readable behavior are covered by focused regressions and manual CLI checks.
- [ ] The post-1.0.0 workflow is dogfooded end to end with `uv run kd`; discovered workflow friction is captured as backlog work, and `uv run kd status --check` passes before the epic closes.
- [ ] Every child ticket is closed with full-suite verification before the epic closes.

## Children

- `fe67` — list outside an active session
- `afd2` — ask outside an active session
- `478a` — review with uncommitted changes
- `953a` — queued chat messages
- `bd1f` — runtime and authentication diagnostics
- `20cf` — configured backend consistency across linked worktrees

## Scope Boundary

Backend additions, image input, and council-assisted ticket vetting remain
separate feature work. This epic may harden discovery of provider-owned models
and capabilities, but does not add or pin new model IDs. It is limited to
failure handling, delivery reliability, configuration consistency, diagnostics,
and recovery.

## Worklog

- [2026-08-24 15:11] [codex:f1fe48bc] — Confirmed branch setup and made this a post-1.0.0 dogfooding epic; workflow friction must be captured as backlog work and the readiness gate must pass before closure.
