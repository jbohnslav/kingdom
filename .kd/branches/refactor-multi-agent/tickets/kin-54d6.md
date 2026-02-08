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
- [x] kd agent run --agent <name> --ticket <id> --worktree <path> runs autonomous loop
- [x] Loop: prompt -> backend -> commit -> worklog -> repeat
- [x] Loop stops on: done (tests pass, criteria met), blocked (needs help), stopped, or failed
- [x] Peasant auto-commits as it works (each meaningful chunk)
- [x] Peasant appends decisions, bugs, difficulties to worklog section in ticket
- [x] kd peasant start KIN-042 creates worktree, session, thread, launches harness in background
- [x] kd peasant status shows table: ticket, agent, status, elapsed, last activity
- [x] kd peasant logs KIN-042 shows stdout/stderr
- [x] kd peasant logs KIN-042 --follow tails logs
- [x] kd peasant stop KIN-042 sends SIGTERM, updates status to stopped
- [x] Peasant output written as messages to work thread
- [x] Session file updated with pid, status, timestamps

## Worklog

- Created `src/kingdom/harness.py` with `run_agent_loop()` — autonomous loop that builds prompts from ticket + worklog + directives, calls backend CLI, parses response, auto-commits, appends worklog, updates session, writes to thread
- Prompt builder includes ticket body, existing worklog, new directives from lead, iteration number, and status instructions (DONE/BLOCKED/CONTINUE)
- `parse_status()` extracts agent-reported status from the last STATUS line in response; `extract_worklog_entry()` pulls first paragraph for worklog
- `auto_commit()` stages and commits all changes in the worktree with `--no-verify` (peasant commits shouldn't trigger hooks)
- `get_new_directives()` scans thread for king messages after a high-water mark sequence number
- Signal handler catches SIGTERM for graceful stop; loop respects `stop_requested` flag between iterations
- Refactored `kd peasant` from a single worktree command into a typer subcommand group: `start`, `status`, `logs`, `stop`, `clean`
- `kd peasant start` creates worktree, work thread (seeded with ticket content), log directory, launches harness via `Popen` with `start_new_session=True`, records PID in session
- `kd peasant status` uses Rich table showing ticket, status, PID (with liveness check), elapsed time, last activity
- `kd peasant logs` reads stdout/stderr log files; `--follow` delegates to `tail -f`
- `kd peasant stop` sends SIGTERM and updates session to stopped
- `kd peasant clean` replaces the old `--clean` flag for worktree removal
- Added `kd agent run` CLI command as alternative entry point for the harness
- Decision: used `os.open()`/`os.close()` for log file descriptors passed to `Popen` to satisfy ruff SIM115 (context manager rule) while keeping FDs open for the child process
- 33 harness tests + 15 CLI tests, all 324 tests passing
- Fix: done-gating — harness now runs `pytest -x -q` in worktree when agent reports DONE; if tests fail, overrides to CONTINUE and feeds failure back to agent
- Fix: SIGTERM check added after blocking backend call returns, so stop takes effect even if signal arrives mid-subprocess
- Fix: `auto_commit()` now returns `(bool, str | None)` — checks all git return codes, logs and worklogs commit failures
- Fix: `append_worklog()` inserts entries before the next `## ` heading, not at EOF — entries stay within worklog section bounds
- Fix: added `agent_backend` field to `AgentState`, persisted in `peasant start`, shown as Agent column in `peasant status` table
- Fix: `peasant logs --follow` now tails both stdout.log and stderr.log
- Fix: status table shows "dead" for working peasants whose PID is no longer alive
- 38 harness tests + 15 CLI tests, all 329 tests passing
