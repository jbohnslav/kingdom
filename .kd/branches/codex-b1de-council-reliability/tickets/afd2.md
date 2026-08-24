---
id: "afd2"
status: open
deps: []
links: []
created: 2026-07-10T13:32:00Z
type: bug
priority: 2
parent: b1de
---
# Handle council ask without an active session gracefully

Running kd council ask without an active session raises RuntimeError and prints a full Rich traceback. Expected: concise user-facing error telling the user to run kd start or switch to a tracked branch, with a nonzero exit code and no traceback.

## Acceptance Criteria

- [ ]
