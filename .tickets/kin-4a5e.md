---
id: kin-4a5e
status: open
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

- [ ] kd migrate moves runs to branches
- [ ] Content preserved exactly
- [ ] Warning shown if .kd/runs/ detected
- [ ] Empty .kd/runs/ removed after migration

