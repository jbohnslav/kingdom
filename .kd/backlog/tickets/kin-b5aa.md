---
id: kin-b5aa
status: open
deps: []
links: []
created: 2026-02-13T15:17:02Z
type: task
priority: 2
---
# Enable branch protection on master

Currently anyone (including agents with `--dangerously-skip-permissions`) can push straight to master. Set up GitHub branch protection rules to require PRs for all changes to master. Especially important now that peasants run with elevated permissions.

## Acceptance Criteria

- [ ] Direct pushes to master blocked
- [ ] All changes require a PR
- [ ] PR requires at least one approval before merge
