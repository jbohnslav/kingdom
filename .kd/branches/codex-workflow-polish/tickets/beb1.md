---
id: "beb1"
status: open
deps: []
links: []
created: 2026-08-02T14:08:00Z
type: task
priority: 2
parent: 329d
---
# Fix tk list --parent table rendering and hierarchy context

Dogfooding `kd tk list --parent c759` with six children produced a malformed Rich
table: doubled border columns, the title column disappeared, and the location text
was truncated beyond usefulness. Parent-filtered output is central to epic work and
should prioritize child identity/title/dependency state over redundant location.

## Acceptance Criteria

- [ ] `kd tk list --parent ID` renders valid borders at narrow, normal, and wide terminal widths.
- [ ] ID, status, title, and blocking dependencies remain visible in the default parent view.
- [ ] Redundant location is hidden or compacted when all rows share the current branch.
- [ ] Long titles/dependency lists wrap or truncate intentionally with no missing header.
- [ ] A regression test covers the observed six-child output shape.
- [ ] Human and JSON output continue to agree on the selected children.
