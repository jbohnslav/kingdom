---
from: claude
to: king
timestamp: 2026-02-17T11:07:17Z
---

The release workflow is already set up and the trusted publisher is configured. To publish the first version, you just need to merge this branch to `master` with the version bump that Codex already made.

Let me check the current state of things.The version bump is staged but not committed yet, and there are no commits ahead of `master` on this branch. The changes (name → `kingdom-cli`, version → `0.1.1`) plus the `release.yml` workflow are all uncommitted.

Here's your release path:

1. **Commit everything on this branch** (the `pyproject.toml` name/version change + `.github/workflows/release.yml`)
2. **Open a PR and merge to `master`**
3. The merge commit touches `pyproject.toml` on `master`, so `release.yml` fires automatically — it detects the version changed from `0.1.0` → `0.1.1`, runs `uv build`, creates a GitHub Release with auto-generated changelog, and publishes to PyPI via trusted publishing

That's it. You should also update the `description` in `pyproject.toml` — it still says "Add your description here", which is what'll show up on PyPI. Want me to fix that and get this committed?
