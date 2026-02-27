---
id: "daa3"
status: open
deps: []
links: []
created: 2026-02-26T16:18:44Z
type: task
priority: 1
---
# kd tk move --to branch uses literal string 'branch' instead of resolving current git branch

## Acceptance Criteria

- [ ] `kd tk move <ticket> --to branch` resolves `branch` to the current git branch name, not the literal string `"branch"`
- [ ] Moving with `--to branch` places the ticket file under `.kd/branches/<current-branch>/tickets/`
- [ ] If current branch resolution fails (for example outside a git worktree), command exits non-zero with a clear error
- [ ] Regression test covers the `--to branch` path and prevents reintroducing literal `"branch"` behavior
