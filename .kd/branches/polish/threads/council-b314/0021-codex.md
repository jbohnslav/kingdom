---
from: codex
to: king
timestamp: 2026-02-17T11:08:06Z
---

I’m checking the repo state now so I can give exact publish steps from the current branch, not assumptions. I’ll verify what’s changed and whether anything is already committed.
I found a key detail: the working tree has many unrelated uncommitted edits, and the branch is currently `council-writable` (tracking `master`), not a clean release branch. I’m opening the new `release.yml` now to confirm trigger and behavior before recommending the exact publish sequence.
I verified `release.yml`: a merge to `master` that includes a `pyproject.toml` version change will build with `uv`, create `vX.Y.Z` release notes, and publish to PyPI. I’m running one quick local `uv build` sanity check against the current tree so we can confirm the first publish path is clear.
Current state is ready for first publish once a commit with the version bump lands on `master`.

I verified:
- `pyproject.toml` has `name = "kingdom-cli"` and `version = "0.1.1"`.
- `.github/workflows/release.yml` is set to trigger on pushes to `master` when `pyproject.toml` changes.
- `uv build` succeeds locally.

To publish `0.1.1` now:

```bash
# from repo root
git add pyproject.toml .github/workflows/release.yml
git commit -m "release: rename package to kingdom-cli and bump to 0.1.1"
git push origin HEAD:master
```

If you require PRs, open/merge that commit into `master` instead of direct push.

Then GitHub Actions will automatically:
1. detect version change,
2. build with `uv`,
3. create GitHub Release `v0.1.1` with auto-notes,
4. publish to PyPI via trusted publishing.

You can monitor it in Actions (`Release on Version Bump`) and confirm at:
- GitHub Releases tab
- `https://pypi.org/project/kingdom-cli/`

I can run the commit/push sequence for you next if you want me to do it directly.
