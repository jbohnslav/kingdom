---
id: 5bcd
status: closed
deps: []
links: []
created: 2026-02-13T13:39:46Z
type: task
priority: 2
---
# kd design should print repo-relative path, not absolute

The 'kd design' command currently prints an absolute path (e.g. /Users/jrb/code/kingdom/.kd/branches/foo/design.md). It should print a path relative to the repo root instead (e.g. .kd/branches/foo/design.md). Absolute paths encourage agents to navigate the full filesystem rather than staying relative to their working directory.
