---
id: "bba5"
status: open
deps: []
links: []
created: 2026-09-05T16:48:27Z
type: task
priority: 2
---
# Use canonical uv run kd commands in Kingdom checkout guidance

While dogfooding PR #56, `uv run kd start codex/b1de-council-reliability`
printed `Next: kd tk list --backlog, then kd tk pull <id>`. Inside the Kingdom
source checkout, that guidance conflicts with the required working-tree
invocation and can send developers through a stale globally installed CLI.

## Acceptance Criteria

- [ ] Next-step guidance emitted inside a Kingdom source checkout uses `uv run kd`.
- [ ] Installed-user projects continue to receive concise bare-`kd` guidance.
