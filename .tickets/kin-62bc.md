---
id: kin-62bc
status: open
deps: [kin-8472]
links: []
created: 2026-02-04T21:22:10Z
type: task
priority: 0
assignee: Jim Robinson-Bohnslav
---
# Remove tmux/hand from CLI

Remove all references to legacy modules from CLI before deleting them. Remove tmux/hand imports, kd chat, kd attach commands, hand_command() function.

## Acceptance Criteria

- [ ] No tmux imports in cli.py
- [ ] No hand imports in cli.py
- [ ] kd chat not in --help output
- [ ] kd attach not in --help output
- [ ] kd --help works without errors
- [ ] Existing tests pass (or are updated)

