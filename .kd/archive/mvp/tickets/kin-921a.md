---
id: kin-921a
status: closed
deps: []
links: []
created: 2026-01-26T21:13:04Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# MVP guardrails for Hand+Council

Implement MVP guardrails: add per-pane timeouts + partial-failure synthesis; use unique sentinel line (---KD_END:<uuid>---); avoid raw JSON send-keys by writing temp request file and running council worker via stdin.

## Acceptance Criteria

- [ ] Hand dispatch times out per model and continues with available responses\n- [ ] Unique sentinel line used for completion detection\n- [ ] Prompts sent via temp file + stdin to avoid quoting issues
