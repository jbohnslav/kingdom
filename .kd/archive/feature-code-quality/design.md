# Design: Code Quality Infrastructure

## Goal
Establish lightweight, consistent code quality checks that catch real issues without being overly pedantic. The tooling should be fast, easy to run locally, and enforced in CI.

## Context
Kingdom currently has:
- pytest with 10 test files (~2k lines of tests)
- uv as package manager with lock file
- No linting, formatting, or pre-commit hooks
- No CI pipelines

The codebase is ~3.5k lines of production Python code using modern patterns (type hints, `from __future__ import annotations`).

## Requirements
- Ruff for linting and formatting (fast, single tool)
- Pre-commit hooks that run automatically on commit
- GitHub Actions CI that runs the same checks as pre-commit
- pytest in CI with clear failure reporting
- Reasonable defaults that catch bugs without nitpicking style

## Non-Goals
- Type checking (mypy/pyright) - adds friction without proportional benefit for this codebase size
- 100% coverage requirements
- Strict docstring enforcement
- Complex multi-stage CI pipelines

## Decisions

### Ruff Configuration
Use ruff for both linting and formatting. Enable rule sets that catch real bugs while ignoring stylistic bikeshedding:

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
extend-exclude = ["third-party", ".kd"]

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear (catches common bugs)
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade (modernize syntax)
    "SIM",    # flake8-simplify
    "RUF",    # ruff-specific rules
]
ignore = [
    "E501",   # line too long (let formatter handle)
    "SIM108", # ternary operators (sometimes less readable)
]

```

**Rationale**: This catches unused imports, undefined names, common bugs, and keeps imports sorted - all things that matter. It skips docstring requirements, complexity limits, and other rules that create noise. Vendored code in `third-party/` and internal tooling in `.kd/` are excluded.

### Pre-commit Configuration
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
```

**Rationale**: Keep pre-commit fast by only running essential checks. Ruff handles all Python linting/formatting. The pre-commit-hooks catch common file issues (trailing whitespace, missing newlines, accidentally committed large files).

**Developer setup**: Run `pre-commit install` once after cloning to enable hooks.

### GitHub Actions CI
Single workflow that:
1. Runs `pre-commit run --all-files` (same checks as local)
2. Runs `pytest` with output on failure

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync

      - name: Run pre-commit
        uses: pre-commit/action@v3.0.1

      - name: Run tests
        run: uv run pytest
```

**Rationale**: Using `pre-commit/action` ensures CI runs exactly what developers run locally. Single job keeps CI simple and fast.

### pytest Configuration
Expand existing `pytest.ini` slightly:

```ini
[pytest]
testpaths = tests
addopts = -v --tb=short
```

**Rationale**: Verbose output helps identify which tests ran. Short tracebacks are usually sufficient and reduce noise.

## File Changes
1. `pyproject.toml` - Add ruff configuration, add ruff to dev dependencies
2. `.pre-commit-config.yaml` - New file with hooks
3. `.github/workflows/ci.yml` - New CI workflow
4. `pytest.ini` - Minor expansion

## Open Questions
- Should we add `pytest-cov` for coverage reporting? (lean no - adds noise without enforcement)
- Pin exact versions of pre-commit hooks or use latest? (lean pin - reproducibility)
