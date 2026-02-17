---
from: codex
to: king
timestamp: 2026-02-17T10:53:30Z
---

No built-in auto-tag exists, but you can make it effectively “bump commit only” with one workflow.

Key change from the two-workflow idea: do **everything in one run** on `main` when `pyproject.toml` changes, so you avoid the `GITHUB_TOKEN` “workflow won’t trigger workflow” problem.

```yaml
name: Release on Version Bump

on:
  push:
    branches: [main]
    paths: [pyproject.toml]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # create tag/release
      id-token: write   # PyPI trusted publishing

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Read old/new version
        id: v
        shell: bash
        run: |
          new=$(python - <<'PY'
import tomllib, pathlib
print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])
PY
)
          if git show HEAD^:pyproject.toml > /tmp/prev.toml 2>/dev/null; then
            old=$(python - <<'PY'
import tomllib, pathlib
print(tomllib.loads(pathlib.Path("/tmp/prev.toml").read_text())["project"]["version"])
PY
)
          else
            old=""
          fi
          echo "new=$new" >> "$GITHUB_OUTPUT"
          echo "old=$old" >> "$GITHUB_OUTPUT"
          [ "$new" = "$old" ] && echo "changed=false" >> "$GITHUB_OUTPUT" || echo "changed=true" >> "$GITHUB_OUTPUT"

      - if: steps.v.outputs.changed != 'true'
        run: echo "Version unchanged; skipping release."

      - if: steps.v.outputs.changed == 'true'
        uses: astral-sh/setup-uv@v4

      - if: steps.v.outputs.changed == 'true'
        run: uv build

      - name: Create GitHub Release + auto notes
        if: steps.v.outputs.changed == 'true'
        uses: softprops/action-gh-release@v2
        with:
          tag_name: v${{ steps.v.outputs.new }}
          target_commitish: ${{ github.sha }}
          generate_release_notes: true
          files: dist/*

      - name: Publish to PyPI
        if: steps.v.outputs.changed == 'true'
        uses: pypa/gh-action-pypi-publish@release/v1
```

So your flow is exactly: bump `version` in `pyproject.toml`, merge to `main`, done.
Also: use `main` (not `master`) if that’s your default branch.
