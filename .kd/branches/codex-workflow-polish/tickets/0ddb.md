---
id: "0ddb"
status: open
deps: []
links: []
created: 2026-08-02T13:58:06Z
type: task
priority: 2
parent: 48dd
---
# Keep tk pull as the canonical backlog-to-work flow

Preserve the useful one-way action that selects backlog work for the active branch
or workspace. Pull is not the same thing as generic movement.

## Acceptance Criteria

- [ ] `tk pull` keeps the ticket ID, Markdown, links, dependencies, and parent/epic relationship.
- [ ] Pull can optionally start/bind the ticket for the calling context without affecting other sessions.
- [ ] Pulling an already-active ticket is idempotent or gives a precise conflict.
- [ ] Help describes pull as backlog-to-work selection.
- [ ] Manual output is checked for a backlog sprint and an epic child.
