# Publish Checklist

Steps to release a new version of `kingdom-cli`.

## Pre-release

Run checkout commands through `uv run` so release validation cannot accidentally
exercise a stale installed `kd`.

1. All tests pass: `uv run pytest`
2. Lint clean: `uv run ruff check .`
3. Documented CLI workflow passes: `bash scripts/smoke.sh`
   This smoke creates an isolated repository and reaches a real `kd done`; it
   does not replace the final `uv run kd done` on the release branch after its
   tickets and epic are closed.
4. Manually inspect the changed human CLI and council-chat TUI surfaces. At
   minimum review root/ticket help, status in human and JSON modes, closure and
   migration help, and the TUI `/status` output.
5. Review the [1.0.0 release notes](releases/1.0.0.md). Every pre-cut blocker and
   dogfood regression must be resolved or explicitly closed with a reason.
6. For the 1.0.0 cut, verify the public `tk move` command and hidden `add-note`
   alias are absent. Their 0.6.x warnings promised removal in 1.0.0 and 0.8.0,
   respectively; retaining either in 1.0.0 breaks the staged-deprecation contract.
7. Refresh the dated [supported host integration matrix](support-matrix.md):
   - capture `claude --version`, `codex --version`, and
     `cursor-agent --version` without starting interactive sessions;
   - use `cursor --version` only when recording desktop-specific evidence;
   - run `uv run pytest tests/test_host_integration_matrix.py`;
   - label fixture/CLI evidence Contract and reserve Live for real host checks;
   - preserve the documented Cursor limits instead of assuming host parity.
8. Bump the version in `pyproject.toml` and update all version references.
9. Close the final release ticket and epic, then run `uv run kd done`. Any open
   ticket or invalid closure evidence means the release is not ready.
10. Commit: `git commit -m "Bump version to X.Y.Z"`

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

Merging a version bump to `master` triggers publication. Do not merge the release
commit until publishing is explicitly authorized.

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
