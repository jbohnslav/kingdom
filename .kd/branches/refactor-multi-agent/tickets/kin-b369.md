---
id: kin-b369
status: open
deps: [kin-54d6]
links: []
created: 2026-02-07T22:34:30Z
type: task
priority: 3
---
# Peasant messaging and supervision

kd peasant msg <ticket> "message" writes a directive to the work thread (peasant picks it up on next loop iteration). kd peasant read <ticket> shows recent messages from the peasant (escalations, status updates). kd peasant review <ticket> is the Hand's final review after peasant signals done — verify tests, review diff and worklog, accept or reject.

## Acceptance
- [x] kd peasant msg KIN-042 "focus on tests" writes directive to thread, peasant picks up on next iteration
- [x] kd peasant read KIN-042 shows peasant's messages (escalations, worklog updates)
- [x] kd peasant review KIN-042 runs pytest + ruff, shows diff + worklog for Hand review
- [x] Hand can accept (ticket closed, branch ready to merge) or reject (feedback sent, peasant resumes)

## Worklog

- Added `kd peasant msg` — writes king directive to work thread via `add_message`; peasant's existing `get_new_directives` picks it up on next iteration
- Added `kd peasant read` — filters thread messages to peasant-only, displays with Rich panels, supports `--last/-n` for pagination
- Added `kd peasant review` — runs pytest + ruff in worktree (or base), shows git diff --stat and worklog; `--accept` closes ticket and sets session to done, `--reject "feedback"` sends directive and sets session back to working
- 14 new tests (29 total in test_cli_peasant.py), 342/342 suite passing, ruff clean
