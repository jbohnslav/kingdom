---
id: "b1de"
status: closed
deps: []
links: []
created: 2026-08-19T21:46:02Z
type: epic
priority: 2
closed_at: 2026-08-24T20:11:33Z
resolution: completed
closed_context: codex:f1fe48bc0e4e0556
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

- [x] Council list and ask commands handle missing active context without tracebacks or ambiguous fallback.
- [x] Council review handles dirty repositories safely and gives an exact recovery path when it cannot proceed.
- [x] Council chat queues messages without losing, overwriting, or silently reordering them.
- [x] Doctor distinguishes an installed agent CLI from runtime, authentication, and configuration failures.
- [x] Repository-configured Council backends remain consistent across primary and linked worktrees, including environments that intentionally use Cursor instead of Codex.
- [x] Provider model and capability checks follow account-visible CLI behavior without putting Kingdom on a hardcoded model-name treadmill.
- [x] Human errors and machine-readable behavior are covered by focused regressions and manual CLI checks.
- [x] The post-1.0.0 workflow is dogfooded end to end with `uv run kd`; discovered workflow friction is captured as backlog work, and `uv run kd status --check` passes immediately after epic closure and before PR creation.
- [x] Every child ticket is closed with full-suite verification before the epic closes.

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
- [2026-08-24 15:16] [codex:f1fe48bc] — Epic execution started after the branch initialization commit; first direct child is fe67, with independent children delegated selectively to native sub-agents.
- [2026-08-24 15:52] [codex:f1fe48bc] — Epic implementation and owner review complete. All six children are closed. Final verification passed: `uv run pytest` (2272 passed, 41 skipped, 1 xfailed), all 38 separately enabled Textual integration tests passed on the Council queue slice, repository-wide Ruff check and format check passed, `git diff --check` passed, and changed CLI commands were manually inspected. Post-1.0 dogfooding captured workflow friction as backlog tickets cc98, bc87, 0ad6, 8828, and 34b7. The first pre-close `uv run kd status --check` correctly failed only because this epic remained in progress; ticket 34b7 records the sequencing ambiguity, and the gate will be rerun immediately after closure.
- [2026-08-24 15:52] [codex:f1fe48bc] — Post-closure readiness gate passed: uv run kd status --check reports 7 closed tickets, zero nonterminal tickets, and Readiness: ready.
- [2026-08-24 16:11] [codex:f1fe48bc] — Release preparation completed for Kingdom 1.0.1. The release notes explicitly preserve this epic's dogfooding purpose and verification covered pre-commit, smoke, focused packaging checks, and the full test suite.

## Lifecycle

- 2026-08-24T19:52:45Z [codex:f1fe48bc0e4e0556] — closed (completed)
- 2026-08-24T20:09:25Z [codex:f1fe48bc0e4e0556] — reopened (previous: completed)
- 2026-08-24T20:11:33Z [codex:f1fe48bc0e4e0556] — closed (completed)
