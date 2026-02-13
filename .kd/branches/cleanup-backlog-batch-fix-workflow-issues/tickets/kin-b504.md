---
id: kin-b504
status: closed
deps: []
links: []
created: 2026-02-13T21:38:03Z
type: task
priority: 3
---
# Design doc approved state

After council reviews a design doc, there's no way to mark it as reviewed or
approved. The doc just exists as a file. A lightweight `kd design approve`
command (or a status field in the design doc frontmatter) would make it clear
whether the design has been through council review or is still a draft.

## Acceptance Criteria

- [ ] Design doc has a way to indicate review status (draft vs approved)
- [ ] `kd status` reflects whether the design has been reviewed
