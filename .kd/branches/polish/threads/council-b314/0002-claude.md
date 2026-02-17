---
from: claude
to: king
timestamp: 2026-02-17T04:41:56Z
---

Here's how to set it up:

**1. Version management**

Use a single source of truth for the version. Since you're using `uv`, your `pyproject.toml` already has the version. You can either:
- Bump it manually before tagging
- Or use a tool like `bump2version` / `python-semantic-release` to automate it

The simplest approach: just edit `pyproject.toml` manually when you're ready to release.

**2. GitHub Actions workflow**

Create `.github/workflows/release.yml` that triggers on tag pushes:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # for trusted publishing
      contents: write  # for creating the GitHub release
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # needed for changelog generation

      - uses: astral-sh/setup-uv@v4

      - run: uv build

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true  # auto-changelog from PR titles

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # uses trusted publishing — no API token needed
```

**3. PyPI trusted publishing**

On pypi.org, go to your project settings and add a "trusted publisher" — point it at your GitHub repo, the workflow filename (`release.yml`), and the environment (leave blank or `release`). This means no API tokens to manage.

**4. The release flow**

Every N PRs when you're ready:

```bash
# bump version in pyproject.toml
# commit it
git tag v0.1.0
git push origin v0.1.0
```

The tag push triggers the workflow. GitHub's `generate_release_notes: true` gives you the auto-changelog built from merged PR titles/descriptions since the last tag. It shows up in the Releases tab.

**5. What you get**

- Releases tab with auto-generated changelogs (grouped by PR)
- Package built and pushed to PyPI via trusted publishing
- No tokens to rotate, no manual PyPI uploads

The key insight is that `generate_release_notes: true` in the `softprops/action-gh-release` action uses GitHub's built-in release notes generator — it pulls from PR titles between tags. So if your PR titles are descriptive, your changelog writes itself.

Want me to look at your current `pyproject.toml` to see if anything needs adjusting for the build/publish setup?
