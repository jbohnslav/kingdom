---
id: "e0eb"
status: closed
deps: []
links: []
created: 2026-02-17T03:04:22Z
type: task
priority: 2
---
# kd chat: inject branch context and tk list into system prompt

ChatApp should inject current branch name and ticket list summary so agents know what we're working on without manual pasting.

## Worklog

- 2026-02-17 03:18 -- Added build_branch_context() to tui/app.py; injects branch name + ticket summary into member preambles
- 2026-02-17 03:18 -- Added 6 tests in TestBuildBranchContext class
- 2026-02-17 03:25 -- Fixed pre-existing test failures from cursor backend removal and output message changes
