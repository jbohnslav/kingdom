---
from: codex
to: king
timestamp: 2026-02-17T11:11:24Z
---

I’m going to inspect `pyproject.toml` and the release workflow so I can give a concrete prereq checklist based on what’s actually missing right now, not a generic list.
I confirmed the workflow and metadata file; next I’m checking top-level docs/license files so we can define the full publish-prereqs scope precisely.
I found additional concrete gaps: README still says MIT and dev-only install flow, and there’s no top-level `LICENSE` file yet. I’m doing one quick pass for packaging/metadata hygiene (keywords/classifiers/URLs/type marker) before I propose the final prereq checklist.
I found the new backlog ticket is just a stub (`02b5`) with empty acceptance criteria. I’m going to flesh it into a concrete publish-readiness checklist so this can be executed without ambiguity.
I also want to catch hidden “works in repo, breaks when installed” issues before first PyPI push. I’m scanning for hardcoded repo-relative paths and runtime file assumptions.
Expanded `02b5` into a concrete checklist in `.kd/backlog/tickets/02b5.md`.

Most important “what else” items (beyond license/description/topics) are:

1. Metadata completeness in `pyproject.toml`: `license`, `authors`, `keywords`, `classifiers`, `urls`.
2. Legal consistency: add root `LICENSE` (Apache-2.0) and fix `README.md` (it currently says MIT).
3. Runtime dependency audit: move non-runtime deps out of `[project].dependencies` (notably `pytest-asyncio`).
4. Packaging quality gates: `uv build` plus `twine check` on `dist/*`.
5. Real install smoke test from wheel in clean env: confirm `kd --help` works.
6. Release UX: add `.github/release.yml` so GitHub auto-notes are grouped by labels.
7. Repo metadata: set GitHub description + topics for discoverability.
8. Publish runbook: short first-release checklist in `docs/`.

One release-specific gotcha: your workflow only publishes when version changes, so the prereq PR that you want to publish must include a version bump.
