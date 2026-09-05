---
id: "cbbd"
status: closed
deps: [990d]
links: []
created: 2026-08-03T12:27:00Z
type: task
priority: 2
closed_at: 2026-08-03T19:27:49Z
resolution: completed
closed_context: codex:a775e0448cdb5a76
assignee: codex:a775e0448cdb5a76
parent: c759
---
# Cut Kingdom 1.0 major version release

## Acceptance Criteria

- [x] Package and CLI version surfaces report `1.0.0` consistently.
- [x] Release notes describe the ticket-first workflow, execution-context model,
  typed lifecycle changes, host support, migrations, and staged deprecations.
- [x] Upgrade and rollback instructions are verified against an existing `0.6.x`
  `.kd` repository without losing Markdown history.
- [x] The supported-host matrix, peasant/lord regression, full suite, and `kd done`
  release evidence are complete before the version changes.
- [x] The release commit is ready to tag and publish, but publishing remains a
  separate explicitly authorized action.

## Plan

This is the final child of the release-safety epic. It depends on `990d`, which
collects migration, deprecation, integration, and dogfood evidence. Keep the
repository at `0.6.0` while behavior is changing; cut `1.0.0` only after those
gates pass so intermediate development commits do not masquerade as a release.

## Worklog

- 2026-08-03 — Added at the King's request as the final gate for the ticket-first
  refactor. Wired `cbbd → 990d` and changed umbrella `2aed` to depend on `cbbd`
  instead of `990d`.
- [2026-08-03 15:27] [codex:a775e044] — Kingdom 1.0.0 source and artifact cut completed without publishing. Package and lock metadata now report 1.0.0 and declare click>=8.3.1 directly; root `kd --version` and `python -m kingdom --version` both report `kd 1.0.0`. The public move and hidden add-note routes are unregistered while internal movement plus pull/defer/archive coverage remains. Final docs describe the ticket-first/context/typed-lifecycle workflow, migrations, resolved dogfood issues, host evidence, command removals, and explicit publication boundary. The release workflow is workflow_dispatch-only, rejects non-master or mismatched-version dispatches, requires checked-in notes, validates artifacts, and publishes only after manual authorization.

  Pre-version evidence was completed under 990d and its dependencies: existing 0.6.x repository migration/rollback preserved raw Markdown history; host matrix and peasant/lord defaults passed; isolated smoke reached real kd done. Final integrated verification: 2,168 passed, 38 skipped, 1 expected xfail; whole-tree Ruff and format passed; every pre-commit hook passed; final smoke passed through three completed resolutions and kd done. `uv build` produced 1.0.0 wheel/sdist and Twine passed both. A fresh Python 3.12 venv installed the wheel with direct Requires-Dist click, ran `kd --version`, `python -m kingdom --version`, help, isolated start/status, removed-command checks, and read-only doctor successfully. Manual root/ticket help and removed command failures were reviewed. No tag, push, release workflow dispatch, or publication occurred; user-owned untracked 64a8.md was not modified or staged.

## Lifecycle

- 2026-08-03T19:27:49Z [codex:a775e0448cdb5a76] — closed (completed)
