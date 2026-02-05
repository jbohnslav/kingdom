# Breakdown: Code Quality Infrastructure

## Phase 1: Core Tooling

### T1: Configure Ruff in pyproject.toml
**Priority:** 0 (highest - foundation for everything else)
**Dependencies:** none

Add ruff configuration and dev dependency to `pyproject.toml`:
- Add `ruff` to dev dependencies
- Add `[tool.ruff]` configuration with target-version, line-length, extend-exclude
- Add `[tool.ruff.lint]` with selected rule sets (E, W, F, I, B, C4, UP, SIM, RUF)
- Add ignore list for E501, SIM108

**Acceptance Criteria:**
- [ ] `ruff` added to dev dependencies in pyproject.toml
- [ ] `[tool.ruff]` section configured per design
- [ ] `[tool.ruff.lint]` section with correct select/ignore
- [ ] `uv sync` installs ruff successfully
- [ ] `ruff check .` runs without config errors

---

### T2: Run initial Ruff fixes
**Priority:** 0
**Dependencies:** T1

Apply ruff fixes to existing codebase:
- Run `ruff check --fix .` to auto-fix lint issues
- Run `ruff format .` to format all Python files
- Review and commit changes

**Acceptance Criteria:**
- [ ] `ruff check .` passes with no errors
- [ ] `ruff format --check .` passes with no changes needed
- [ ] All existing tests still pass
- [ ] Changes committed

---

## Phase 2: Git Hooks

### T3: Create pre-commit configuration
**Priority:** 1
**Dependencies:** T2

Create `.pre-commit-config.yaml` with hooks:
- ruff-pre-commit for linting (with --fix)
- ruff-format for formatting
- pre-commit-hooks for trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, check-merge-conflict

**Acceptance Criteria:**
- [ ] `.pre-commit-config.yaml` exists with correct content
- [ ] `pre-commit run --all-files` passes
- [ ] Hooks use pinned versions per design

---

### T4: Add pre-commit to dev dependencies
**Priority:** 1
**Dependencies:** T3

Update `pyproject.toml` to include pre-commit:
- Add `pre-commit` to dev dependencies
- Document setup in README or CLAUDE.md

**Acceptance Criteria:**
- [ ] `pre-commit` in dev dependencies
- [ ] `uv sync` installs pre-commit
- [ ] Developer setup instructions documented

---

## Phase 3: CI Pipeline

### T5: Create GitHub Actions CI workflow
**Priority:** 1
**Dependencies:** T3

Create `.github/workflows/ci.yml`:
- Trigger on push to master and PRs to master
- Single job that installs deps, runs pre-commit, runs pytest
- Use actions/checkout, astral-sh/setup-uv, actions/setup-python, pre-commit/action

**Acceptance Criteria:**
- [ ] `.github/workflows/ci.yml` exists with correct content
- [ ] Workflow syntax validates (`gh workflow view` or similar)
- [ ] CI matches local pre-commit + pytest behavior

---

### T6: Expand pytest.ini configuration
**Priority:** 2
**Dependencies:** none (can run anytime)

Update `pytest.ini` with improved defaults:
- Add `testpaths = tests`
- Add `addopts = -v --tb=short`

**Acceptance Criteria:**
- [ ] `pytest.ini` updated per design
- [ ] `pytest` runs with verbose output and short tracebacks
- [ ] All tests pass

---

## Dependency Graph

```
T1 (configure ruff)
 └──> T2 (run fixes)
       └──> T3 (pre-commit config)
             ├──> T4 (pre-commit dep)
             └──> T5 (CI workflow)

T6 (pytest.ini) ──> (no deps, anytime)
```

## Summary

- **6 tickets** total
- **Phase 1:** 2 tickets (T1, T2) - Core ruff setup and initial fixes
- **Phase 2:** 2 tickets (T3, T4) - Git hooks
- **Phase 3:** 2 tickets (T5, T6) - CI and pytest improvements

**Critical path:** T1 → T2 → T3 → T5

**Parallelization opportunities:**
- T6 can run anytime
- T4, T5 can run in parallel after T3
