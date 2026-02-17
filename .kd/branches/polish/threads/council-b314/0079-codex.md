---
from: codex
to: king
timestamp: 2026-02-17T13:22:28Z
---

I’m applying the remaining publish nits now: I’ll patch `pyproject.toml` to add the Apache classifier and remove the redundant `textual` dependency-group entry, then run quick validation.
I confirmed the remaining gaps: Apache license classifier is still missing and `textual` is duplicated in a dependency group. I’m patching `pyproject.toml` now, then I’ll verify GitHub repo description/topics via `gh`.
`pyproject.toml` is patched. I’m now running `uv build` and `twine check` to verify release metadata/artifacts are clean after the changes.
Build surfaced an important packaging constraint: with current `setuptools`, adding the Apache license classifier breaks builds (`InvalidConfigError` under PEP 639). I’m fixing this by removing that classifier and adding explicit `license-files = ["LICENSE"]` instead, then re-running build/check.
Packaging checks are now passing again; the classifier had to be removed due PEP 639, and license coverage is handled via `license-files`. I’m now explicitly setting the GitHub repo description/topics with `gh` so item 3 is completed, then I’ll summarize exact next publish step (version bump path).
I’ve applied the metadata and repo setting updates. I’m running the full test suite once more so we can say this is fully clean before merge/publish.
Done. I fixed the remaining pre-publish nits and verified everything.

- Updated `pyproject.toml`:
  - Kept `textual` in main runtime deps and removed redundant `[dependency-groups].chat`.
  - Added `license-files = ["LICENSE"]`.
  - Kept description/changelog URL aligned for PyPI.
- Tried adding the Apache classifier, but `setuptools` now rejects license classifiers with SPDX license expressions (PEP 639).
  - So this is intentionally handled via `license = "Apache-2.0"` + `license-files`, which builds cleanly.
- Explicitly set GitHub repo metadata with `gh repo edit`:
  - Description: set
  - Topics: `agents, ai, cli, development-workflow, multi-model, python`
- Verified release readiness:
  - `uv build` passed
  - `uvx twine check dist/*` passed
  - `uv run pytest -q` passed (`1098 passed, 29 skipped, 1 xfailed`)

`pyproject.toml` now has the needed cleanup, and version is already `0.1.1`, so once this lands on `master`, the release workflow can publish.
