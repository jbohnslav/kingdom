---
from: codex
to: king
timestamp: 2026-02-17T12:59:11Z
---

I’m checking the current repo state directly so the pre-public checklist is concrete, not generic. I’ll verify `pyproject.toml`, release workflow, and what metadata/docs files are still missing.
I confirmed core docs/files exist; next I’m reading `pyproject.toml`, README, and release config to identify the last blockers before first public publish.
I’ve verified the current files. I’m checking `docs/publish-checklist.md` and ticket `02b5` next so I can call out only truly missing prereqs.
I found a few likely gaps already (license classifier, changelog URL, and description wording mismatch). I’m doing one quick code scan for dependency/runtime traps before I propose the final pre-release list.
Build and `twine check` both pass. I’m running a clean wheel install smoke test now, including `kd chat --help`, to catch any “README flow fails on fresh install” issues before release.
I validated baseline commands in a clean install; now I’m checking `kd chat --new` in that same clean env. If it fails without extra deps, that’s a true pre-public blocker because it’s in the primary README flow.
The clean `kd chat --new` probe hit an early failure path; I’m rerunning with full output capture so we can see whether it’s a chat dependency issue or just repo setup preconditions.
I found a real blocker: a fresh install cannot run `kd chat --new` because `textual` is not installed by default, but README’s main flow requires chat. I’m running `ruff` and tests now to surface any remaining release blockers.
I checked the ticket and current repo state directly. Before first public release, I’d still do these:

1. **Fix a real install-flow blocker**
`uv tool install kingdom-cli` currently does **not** install `textual`, so `kd chat --new` fails on a fresh install (`The 'textual' package is required for kd chat.`).
Decide one:
- make `textual` a runtime dependency in `pyproject.toml`, or
- make a real optional extra and update README install to include it.

2. **Tighten PyPI metadata in `pyproject.toml`**
- Update description to match current positioning (`markdown file-based`, not `git-native`).
- Add license classifier (`License :: OSI Approved :: Apache Software License`).
- Add `Changelog` URL under `[project.urls]` (ticket asks for it).

3. **Set GitHub repo description (manual)**
Topics are already set, but repo description is currently empty.

4. **Keep version bump in the release PR**
Workflow only publishes when `version` changes, so prereq fixes must land with the bump commit.

5. **Run first-release validation once on final commit**
Already verified now: `uv build`, `twine check`, `ruff`, and full `pytest` pass.
Re-run after final edits, then merge.

Most other prereqs are already in place (`LICENSE`, README rewrite, release workflow, `.github/release.yml`, publish checklist, architecture doc).

I can patch items 1–3 now in one PR-ready change.
