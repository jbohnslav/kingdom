---
id: kin-c039
status: closed
deps: [kin-55a3, kin-af68]
links: []
created: 2026-02-04T21:22:44Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Update kd start command

Update kd start for branch-based structure. Use current git branch if no arg. Normalize branch name. Create .kd/branches/<normalized>/. Set .kd/current. Store original branch in state.json. Handle edge cases: detached HEAD, existing current, collision.

## Acceptance Criteria

- [ ] kd start feature/oauth creates .kd/branches/feature-oauth/
- [ ] state.json contains branch name
- [ ] .kd/current contains normalized name
- [ ] No tmux references
- [ ] Works with current git branch if no arg
- [ ] Handles detached HEAD gracefully
- [ ] Handles existing current gracefully
