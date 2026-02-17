---
from: claude
to: king
timestamp: 2026-02-17T10:52:45Z
---

There's no built-in auto-tag, but you can set one up easily with a second workflow that watches for version bumps on `master`:

```yaml
name: Auto-tag on version bump

on:
  push:
    branches: [master]
    paths: [pyproject.toml]

jobs:
  tag:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Get version
        id: ver
        run: |
          version=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
          echo "version=$version" >> "$GITHUB_OUTPUT"
      - name: Tag if new
        run: |
          tag="v${{ steps.ver.outputs.version }}"
          if ! git rev-parse "$tag" >/dev/null 2>&1; then
            git tag "$tag"
            git push origin "$tag"
          fi
```

This fires when `pyproject.toml` changes on `master`. It reads the version, checks if that tag already exists, and creates it if not. The new tag then triggers your release workflow.

So your entire release flow becomes: bump version in `pyproject.toml`, merge to `master`, and everything else happens automatically — tag creation, GitHub Release with auto-changelog, build, PyPI publish.

One thing to watch: make sure the auto-tag workflow has permission to trigger other workflows. By default, actions using the built-in `GITHUB_TOKEN` **won't** trigger other `on: push` workflows (to prevent infinite loops). You'd need either:

- A **fine-grained PAT** stored as a repo secret, used for the `git push origin "$tag"` step
- Or skip the auto-tag workflow entirely and just run `git tag` locally after your bump commit — honestly the simplest option

Given that you're manually deciding when to release anyway, I'd lean toward just aliasing the local tag+push:

```bash
# in your shell rc or a Makefile
alias release='git tag v$(grep "^version" pyproject.toml | head -1 | sed "s/.*\"\(.*\)\"/\1/") && git push origin --tags'
```

Then it's: bump version, commit, merge, run `release`. One extra command but no PAT management.
