---
id: kin-cebe
status: open
deps: []
links: []
created: 2026-02-09T18:48:40Z
type: task
priority: 1
---
# Review --reject auto-relaunch and dead peasant warnings

Two supervision UX issues from the kin-41f9 smoke test.

## 1. `kd peasant review --reject` must auto-relaunch

Currently `--reject` sends feedback to the thread and sets status to "working", but the harness process is already dead. The user has to manually run `kd peasant start` again. If the peasant process has exited, `--reject` should automatically restart the harness so it picks up the feedback immediately.

## 2. `kd peasant msg` must warn on dead peasant

Currently `kd peasant msg` writes to the thread silently even when the harness isn't running. The message will never be read. Should warn the user that the peasant is not running and the message won't be picked up until the peasant is restarted.

## Acceptance Criteria

- [ ] `kd peasant review --reject "fix X"` restarts the harness if the peasant process has exited
- [ ] After reject-relaunch, peasant picks up the feedback on its next iteration
- [ ] `kd peasant msg` warns when the target peasant is not running (dead/done/stopped)
- [ ] `kd peasant msg` still writes the message to the thread (so it's there when peasant restarts)
