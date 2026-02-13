---
id: kin-10ee
status: open
deps: []
links: []
created: 2026-02-13T13:35:18Z
type: task
priority: 1
---
# Fix kd work integration issues from council review

Cursor implemented kd work and the peasant start refactor. Architecture is correct but has integration gaps: (1) 3 test failures in test_cli_peasant.py - mock launch_harness no longer exists, update to mock subprocess.Popen. (2) 7 test failures in test_council.py - council preamble injection changes expected prompt shapes. (3) kd work ignores --base flag - _resolve_peasant_context hardcodes Path.cwd(). (4) Duplicated Popen boilerplate - extract launch_work_background helper. (5) No thread seed in interactive kd work. (6) Dead code - remove harness.py main() and empty kd agent subcommand group.

## Worklog

- [13:42] Backend error: Error: Claude Code cannot be launched inside another Claude Code session.
Nested sessions share runtime resources and will crash all active sessions.
To bypass this check, unset the CLAUDECODE environment variable.
