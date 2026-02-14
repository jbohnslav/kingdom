---
id: cebe
status: closed
deps: []
links: []
created: 2026-02-09T18:48:40Z
type: task
priority: 2
---
# Review --reject auto-relaunch and dead peasant warnings

Two supervision UX issues from the 41f9 smoke test.

## 1. `kd peasant review --reject` must auto-relaunch

Currently `--reject` sends feedback to the thread and sets status to "working", but the harness process is already dead. The user has to manually run `kd peasant start` again. If the peasant process has exited, `--reject` should automatically restart the harness so it picks up the feedback immediately.

## 2. `kd peasant msg` must warn on dead peasant

Currently `kd peasant msg` writes to the thread silently even when the harness isn't running. The message will never be read. Should warn the user that the peasant is not running and the message won't be picked up until the peasant is restarted.

## Acceptance Criteria

- [x] `kd peasant review --reject "fix X"` restarts the harness if the peasant process has exited
- [x] After reject-relaunch, peasant picks up the feedback on its next iteration
- [x] `kd peasant msg` warns when the target peasant is not running (dead/done/stopped)
- [x] `kd peasant msg` still writes the message to the thread (so it's there when peasant restarts)

## Worklog

- Extracted `launch_harness()` helper from `peasant_start` to reuse in reject path
- Reject path checks if PID is alive; if dead, relaunches harness with same agent config
- If alive, just sends feedback and lets running peasant pick it up
- `peasant_msg` checks session state + PID liveness after writing; warns if not running
- Added 4 new tests: reject-relaunch, reject-no-relaunch-if-alive, msg-warns-dead, msg-no-warning-alive
- No difficulties — `agent_backend` is stored in session state so relaunch has all needed info
