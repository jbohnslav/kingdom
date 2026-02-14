---
id: b5aa
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

## Implementation Notes (council)

**This is a GitHub admin task, not a code change.** Use `gh api` or the GitHub UI to set branch protection rules.

**Approach:**
- Use `gh api` to enforce branch protection on master
- Optionally create a `scripts/protect_branch.sh` for reproducibility

**Gotchas:**
- Requires admin permissions on the GitHub repo
- After enabling, all agents (including peasants with `--dangerously-skip-permissions`) will be blocked from direct pushes — that's the goal
- Consider whether to also require status checks (CI passing before merge)
