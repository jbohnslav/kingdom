---
from: claude
to: king
timestamp: 2026-02-17T10:57:11Z
---



Looking at the conversation, the King wants me to create the release workflow. Let me check the current state of things first.Default branch is `master`, repo is `jbohnslav/kingdom`. Let me check the existing CI workflow and build system quickly.Good, CI already uses `uv`. I'll go with Codex's single-workflow approach — it's the cleanest since it avoids the `GITHUB_TOKEN` can't-trigger-other-workflows problem. Bump version on `master`, everything happens in one job.Done. Created `.github/workflows/release.yml`. Here's what it does:

**Trigger:** Any push to `master` that touches `pyproject.toml`.

**Logic:**
1. Compares the version in `pyproject.toml` against the previous commit — if unchanged, skips everything
2. Builds with `uv build`
3. Creates a GitHub Release with auto-generated changelog (from PR titles since last tag)
4. Publishes to PyPI via trusted publishing (no API token needed)

**Your release flow:** Bump `version` in `pyproject.toml`, merge to `master`. That's it.

**One thing you still need to do on PyPI:** Set up [trusted publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) for this repo. On pypi.org, go to your project → Settings → Publishing → Add trusted publisher:
- Owner: `jbohnslav`
- Repository: `kingdom`
- Workflow: `release.yml`
- Environment: (leave blank)

You'll need to register the `kingdom` package on PyPI first if it doesn't exist yet — you can do that as part of adding the trusted publisher ("pending publisher" flow).
