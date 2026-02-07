---
id: kin-54d6
status: open
deps: [kin-56a5, kin-304a, kin-2d8e]
links: []
created: 2026-02-07T22:34:21Z
type: task
priority: 2
---
# Peasant execution

Agent harness (kd agent run) that runs an autonomous loop: build prompt from ticket + worklog + directives, call backend, apply changes, commit, run tests, append to worklog, update session, write to thread. Loop continues until done (acceptance criteria met, tests pass), blocked (needs help), or stopped. kd peasant start <ticket> creates worktree + branch, creates session file, creates work thread, seeds with ticket_start message, launches harness as background process. kd peasant status shows table of active peasants. kd peasant logs <ticket> [--follow] tails subprocess logs. kd peasant stop <ticket> kills process. Ticket file has a pre-formatted worklog section that the peasant appends to as it works.

## Acceptance
- [ ] kd agent run --agent <name> --ticket <id> --worktree <path> runs autonomous loop
- [ ] Loop: prompt -> backend -> commit -> worklog -> repeat
- [ ] Loop stops on: done (tests pass, criteria met), blocked (needs help), stopped, or failed
- [ ] Peasant auto-commits as it works (each meaningful chunk)
- [ ] Peasant appends decisions, bugs, difficulties to worklog section in ticket
- [ ] kd peasant start KIN-042 creates worktree, session, thread, launches harness in background
- [ ] kd peasant status shows table: ticket, agent, status, elapsed, last activity
- [ ] kd peasant logs KIN-042 shows stdout/stderr
- [ ] kd peasant logs KIN-042 --follow tails logs
- [ ] kd peasant stop KIN-042 sends SIGTERM, updates status to stopped
- [ ] Peasant output written as messages to work thread
- [ ] Session file updated with pid, status, timestamps
