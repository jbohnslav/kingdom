---
id: kin-a8ac
status: open
deps: [kin-c039]
links: []
created: 2026-02-04T21:22:45Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Update kd done command

Move .kd/branches/<name>/ to .kd/archive/<name>/. Clear .kd/current. Update state.json with done_at and status. Clean up associated worktrees. Handle archive collision with timestamp suffix.

## Acceptance Criteria

- [ ] kd done moves branch folder to archive
- [ ] .kd/current is cleared
- [ ] Archived folder preserves all content
- [ ] Worktrees cleaned up
- [ ] Handles archive collision (adds suffix)

