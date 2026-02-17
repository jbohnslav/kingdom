---
from: codex
to: king
timestamp: 2026-02-17T04:42:53Z
---

I’d do this as a **release-driven pipeline** (not PR-count automation), so you choose cadence every N PRs and keep it predictable.

1. Merge PRs normally.
2. When you want a release (every N PRs), bump version in a small “release PR” and merge it.
3. Create a GitHub Release with tag `vX.Y.Z` and click **Generate release notes** (or use `gh release create vX.Y.Z --generate-notes`).
4. A GitHub Action on `release.published` builds and publishes to PyPI.

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: python -m pip install --upgrade build
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/*

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist
      - uses: pypa/gh-action-pypi-publish@release/v1
```

5. In PyPI, configure **Trusted Publisher** for this repo/workflow/environment (`pypi`) so no API token is needed.
6. Add `.github/release.yml` to control changelog sections (features/fixes/deps) via labels.

```yaml
# .github/release.yml
changelog:
  categories:
    - title: Features
      labels: [enhancement, feature]
    - title: Fixes
      labels: [bug, fix]
    - title: Dependencies
      labels: [dependencies]
    - title: Other
      labels: ["*"]
  exclude:
    labels: [ignore-for-release]
```

If you want strict “auto-release every N merged PRs,” that’s possible, but I’d avoid it initially because it’s brittle. This release-PR + release-tag flow is simpler and production-safe.

Sources:
- GitHub auto release notes: https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes
- GitHub release event triggers: https://docs.github.com/en/actions/automating-your-workflow-with-github-actions/events-that-trigger-workflows
- PyPA guide (GitHub Actions + PyPI trusted publishing): https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
- PyPI trusted publishers: https://docs.pypi.org/trusted-publishers/adding-a-publisher/
- `gh release create --generate-notes`: https://cli.github.com/manual/gh_release_create
