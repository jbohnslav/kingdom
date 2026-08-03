# Publish Checklist

Steps to release a new version of `kingdom-cli`.

## Pre-release

Run checkout commands through `uv run` so release validation cannot accidentally
exercise a stale installed `kd`.

1. All tests pass: `uv run pytest`
2. Lint clean: `uv run ruff check .`
3. Documented CLI workflow passes: `bash scripts/smoke.sh`
4. Bump version in `pyproject.toml`
5. Update any version references (if applicable)
6. Commit: `git commit -m "Bump version to X.Y.Z"`

## Build & Validate

```bash
uv build
uv run --with twine python -m twine check dist/*
```

Both sdist and wheel should show `PASSED`.

## Smoke Test

```bash
uv venv /tmp/kd-smoke --python 3.12
uv pip install --python /tmp/kd-smoke/bin/python dist/kingdom_cli-X.Y.Z-py3-none-any.whl
/tmp/kd-smoke/bin/kd --help
/tmp/kd-smoke/bin/kd doctor
rm -rf /tmp/kd-smoke
```

## Merge & Release

1. Push branch and merge PR to `master`
2. The `Release on Version Bump` workflow triggers automatically when `pyproject.toml` changes on `master`
3. Verify:
   - GitHub Release created at `https://github.com/jbohnslav/kingdom/releases`
   - Tag `vX.Y.Z` exists
   - sdist and wheel attached to the release
   - PyPI package updated at `https://pypi.org/project/kingdom-cli/`

## Post-release

```bash
pip install kingdom-cli==X.Y.Z
kd --help
```

Confirm the published version installs and runs. Bare `kd` is intentional in
this post-release check: it verifies the installed artifact, not checkout code.
