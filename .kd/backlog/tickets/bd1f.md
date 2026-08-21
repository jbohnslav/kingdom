---
id: "bd1f"
status: open
deps: []
links: []
created: 2026-03-06T14:12:04Z
type: task
priority: 2
parent: b1de
---
# Expand kd doctor to catch agent runtime/auth failures, not just installed CLIs

## Acceptance Criteria

- [ ]

## Worklog

- [2026-08-03 15:47] [codex:a775e044] — Audit on 2026-08-03 during e8cc reconciliation: this ticket remains unresolved. It was intentionally left open; no lifecycle change was made.
- [2026-08-03 15:47] [codex:a775e044] — Current `kd doctor` covers CLI installation/probe failures, config validation, and repository metadata checks. Runtime authentication failures are handled fail-fast by completed ticket bc0c, but doctor itself does not perform the broader runtime/auth checks requested here.
