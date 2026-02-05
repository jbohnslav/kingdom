---
id: kin-ace6
status: closed
deps: [kin-62bc]
links: []
created: 2026-02-04T21:22:24Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Add branch name normalization

Add normalize_branch_name(), branches_root(), branch_root(), backlog_root(), archive_root() to state.py. Normalization: slashes to dashes, lowercase, ASCII only, collision detection.

## Acceptance Criteria

- [ ] normalize_branch_name('feature/oauth-refresh') returns 'feature-oauth-refresh'
- [ ] normalize_branch_name('JRB/Fix-Bug') returns 'jrb-fix-bug'
- [ ] No double dashes in output
- [ ] Collision detection works
- [ ] Unit tests for edge cases
