---
id: "aeec"
status: open
deps: []
links: []
created: 2026-09-05T21:30:56Z
type: task
priority: 2
---
# Remove inert kd start --force compatibility option

The option is accepted but never read in `src/kingdom/cli/__init__.py:175`. Manual `uv run kd start --help` advertises it solely for compatibility. Identified during audit 6509; see `docs/slop-audit-2026-09-05.md`, finding 10.

## Acceptance Criteria

- [ ] Remove the inert option and obsolete compatibility tests while preserving idempotent start behavior.
- [ ] Manually verify help and run the full test suite.
