---
id: "d1fa"
status: open
deps: []
links: [0240]
created: 2026-03-05T16:22:24Z
type: task
priority: 1
---
# Track kingdom hook source in repo and sync installer output

The canonical kingdom hook logic currently lives in .claude/hooks, which is gitignored and invisible in peasant worktrees. Move canonical source into tracked project code and make kd plugin enable install/sync runtime hook files from that source.

## Acceptance Criteria

- [ ] Canonical hook source is moved to a tracked path in the repo (not under .claude/).
- [ ] `kd plugin enable` installs or syncs `.claude/hooks/kd-workflow.sh` from tracked source.
- [ ] `kd plugin disable` behavior remains unchanged for hook registration cleanup.
- [ ] Installer handles updates idempotently and preserves executable permissions.
- [ ] Tests cover install/sync path and keep existing plugin enable/disable behavior green.
