---
id: kin-7bd0
status: closed
deps: [kin-9fe2]
links: []
created: 2026-02-05T00:32:40Z
type: task
priority: 1
---
# Run initial Ruff fixes on codebase

Apply ruff fixes to existing codebase:
- Run `ruff check --fix .` to auto-fix lint issues
- Run `ruff format .` to format all Python files
- Review and commit changes

## Acceptance Criteria

- [ ] `ruff check .` passes with no errors
- [ ] `ruff format --check .` passes with no changes needed
- [ ] All existing tests still pass
- [ ] Changes committed
