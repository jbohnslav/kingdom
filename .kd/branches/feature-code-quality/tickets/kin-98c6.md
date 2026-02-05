---
id: kin-98c6
status: open
deps: []
links: []
created: 2026-02-05T00:32:42Z
type: task
priority: 2
---
# Expand pytest.ini configuration

Update `pytest.ini` with improved defaults:
- Add `testpaths = tests`
- Add `addopts = -v --tb=short`

## Acceptance Criteria

- [ ] `pytest.ini` updated per design
- [ ] `pytest` runs with verbose output and short tracebacks
- [ ] All tests pass
