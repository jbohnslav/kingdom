---
id: "cbbd"
status: open
deps: [990d]
links: []
created: 2026-08-03T12:27:00Z
type: task
priority: 2
parent: c759
---
# Cut Kingdom 1.0 major version release

## Acceptance Criteria

- [ ] Package and CLI version surfaces report `1.0.0` consistently.
- [ ] Release notes describe the ticket-first workflow, execution-context model,
  typed lifecycle changes, host support, migrations, and staged deprecations.
- [ ] Upgrade and rollback instructions are verified against an existing `0.6.x`
  `.kd` repository without losing Markdown history.
- [ ] The supported-host matrix, peasant/lord regression, full suite, and `kd done`
  release evidence are complete before the version changes.
- [ ] The release commit is ready to tag and publish, but publishing remains a
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
