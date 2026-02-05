---
id: kin-35c0
status: open
deps: [kin-8016]
links: []
created: 2026-02-05T00:32:41Z
type: task
priority: 1
---
# Create GitHub Actions CI workflow

Create `.github/workflows/ci.yml`:
- Trigger on push to master and PRs to master
- Single job: checkout, setup-uv, setup-python 3.12, uv sync, pre-commit/action, uv run pytest
- Use actions/checkout@v4, astral-sh/setup-uv@v5, actions/setup-python@v5, pre-commit/action@v3.0.1

## Acceptance Criteria

- [ ] `.github/workflows/ci.yml` exists with correct content
- [ ] Workflow syntax validates
- [ ] CI matches local pre-commit + pytest behavior
