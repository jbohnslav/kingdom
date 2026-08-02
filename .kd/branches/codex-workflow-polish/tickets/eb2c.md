---
id: "eb2c"
status: open
deps: [f122, 2877]
links: []
created: 2026-08-02T13:58:23Z
type: task
priority: 2
parent: 329d
---
# Make kd start idempotent and ticket-epic-first

Let `kd start` initialize or resume the workspace without asserting that one branch,
one design document, and one current task are the whole unit of work.

## Acceptance Criteria

- [ ] Running `kd start` in an initialized workspace is safe and reports what already exists.
- [ ] The default path does not scaffold or require `design.md`.
- [ ] Existing branch/backlog organization and `tk pull` remain supported.
- [ ] Multiple execution contexts can start different tickets on the same branch.
- [ ] Any retained `.kd/current` meaning is documented as a branch/workspace default, not session identity.
- [ ] Manual output gives a short useful next action.
