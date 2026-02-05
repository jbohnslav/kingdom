---
id: kin-cdec
status: open
deps: []
links: []
created: 2026-02-05T01:32:05Z
type: task
priority: 2
---
# Make kd start prompt for current branch

Problem: having to switch branches and then run kd start is clunky. Proposal: when kd start is run without a branch, prompt to use the current git branch (or enter a new name) and proceed accordingly. Consider also handling detached HEAD with a prompt.
