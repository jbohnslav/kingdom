---
from: codex
to: king
timestamp: 2026-02-17T10:51:05Z
---

You’re right. For this repo, `uv` should be the default path.

I’d run it like this, manually when you decide to release:

1. Bump `version` in `pyproject.toml` on a release PR, merge.
2. Tag that commit: `git tag -a vX.Y.Z -m "vX.Y.Z"` and push the tag.
3. Tag push triggers one workflow that:
- builds with `uv build`
- creates the GitHub Release with auto-notes
- publishes to PyPI via trusted publishing

```yaml
name: Release

on:
  push:
    tags: ["v*"]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v4
      - run: uv build

      - name: Create GitHub Release (auto changelog)
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

Small hardening I’d add: fail if tag/version mismatch (e.g. tag `v1.4.0` but `pyproject.toml` still `1.3.9`).

So yes: Claude’s shape is closer; just keep it `uv`-native and manual-cadence release tags.
