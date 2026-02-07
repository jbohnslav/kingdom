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

kd peasant msg <ticket> "message" writes a directive to the work thread (peasant picks it up on next loop iteration). kd peasant read <ticket> shows recent messages from the peasant (escalations, status updates). kd peasant manage shows actionable summary: pending escalations, work ready for review, stale workers, ready tickets not yet started. kd peasant review <ticket> is the Hand's final review after peasant signals done — verify tests, review diff and worklog, accept or reject. kd status extended to show active agents and unread escalations.

## Acceptance
- [ ] kd peasant msg KIN-042 "focus on tests" writes directive to thread, peasant picks up on next iteration
- [ ] kd peasant read KIN-042 shows peasant's messages (escalations, worklog updates)
- [ ] kd peasant manage shows escalations, completed work for review, stale workers, ready tickets
- [ ] kd peasant review KIN-042 runs pytest + ruff, shows diff + worklog for Hand review
- [ ] Hand can accept (ticket closed, branch ready to merge) or reject (feedback sent, peasant resumes)
- [ ] kd status shows active agents count and pending escalations
