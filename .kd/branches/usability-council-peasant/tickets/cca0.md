---
id: "cca0"
status: closed
deps: []
links: []
created: 2026-02-16T23:58:07Z
type: task
priority: 2
closed_at: 2026-02-23T21:08:57Z
---
# Integration test: intermediate streaming state (StreamingPanel visible during query)

## Description

Integration test (requires `--run-textual-integration`) that verifies the StreamingPanel lifecycle: it appears when a query starts streaming, updates with content, and gets replaced by a MessagePanel when the response completes.

## Acceptance Criteria

- [ ] Test: StreamingPanel is mounted when streaming starts for a member
- [ ] Test: StreamingPanel content updates as stream deltas arrive
- [ ] Test: StreamingPanel is removed and MessagePanel is mounted when stream finishes
- [ ] Test: Multiple members streaming concurrently each get their own StreamingPanel
- [ ] Tests use Textual pilot and are gated behind `--run-textual-integration`
