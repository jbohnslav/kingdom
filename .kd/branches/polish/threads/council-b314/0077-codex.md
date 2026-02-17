---
from: codex
to: king
timestamp: 2026-02-17T13:20:20Z
---

I’m going to quickly verify Claude’s changes in-tree and then give a concrete “ready-to-publish” next step list from current state.
I validated the test suite end-to-end. I’m doing one quick pass on `pyproject.toml` and release config to call out any remaining sharp edges before you cut the first public release.
Quick state check from my side:

1. Release pipeline is wired and valid.
`release.yml` on `master` + `pyproject.toml` version-change gate + PyPI trusted publishing are all in place.

2. Current branch is publish-ready functionally.
I re-ran tests: `1098 passed, 29 skipped, 1 xfailed`.

3. One metadata nit still worth fixing before first public push.
`pyproject.toml` is missing the Apache classifier:
`"License :: OSI Approved :: Apache Software License"`

4. One cleanup nit (not blocking).
`textual` is now in main dependencies (good), but it also still appears in `[dependency-groups].chat`. Safe, but redundant.

5. Release execution path from here.
Commit the release files (exclude the `.kd/branches/.../threads/*` noise), merge to `master`, and the first publish (`0.1.1`) should run automatically.

If you want, I can make the classifier + dependency-group cleanup now and prepare a clean commit set for merge.
