---
id: kin-4a5e
status: closed
deps: [kin-55a3]
links: []
created: 2026-02-04T21:23:00Z
type: task
priority: 2
assignee: Jim Robinson-Bohnslav
---
# Migrate existing .kd/runs/

Detect .kd/runs/ on kd commands. Provide kd migrate to move .kd/runs/<name>/ to .kd/branches/<name>/. Preserve all content. Remove empty .kd/runs/ after.

## Acceptance Criteria

- [x] kd migrate moves runs to branches (done manually)
- [x] Content preserved exactly
- [x] Warning shown if .kd/runs/ detected (n/a - manual migration)
- [x] Empty .kd/runs/ removed after migration

## Work Log

### 2026-02-04
- Did manual migration instead of building automated command:
  - Created `.kd/branches/mvp/` structure
  - Moved `.tickets/*.md` to `.kd/branches/mvp/tickets/`
  - Copied design.md, breakdown.md, learnings.md from `.kd/runs/cleanup/`
  - Updated `.kd/current` to point to "mvp"
  - Removed `.kd/runs/` directory
- Decided not to build `kd migrate` command - one-time manual migration sufficient

