---
from: claude
to: king
timestamp: 2026-02-17T13:05:08Z
---



Let me check those uv docs to understand the tools installation model, since it affects how we think about the `textual` dependency question.Good — I checked the uv docs and the current `pyproject.toml`. A few observations:

1. **`pyproject.toml` metadata is actually already solid** — the license classifier is there (line 17), the description is already updated to "markdown file-based" (line 4), and the Changelog URL is set (line 30). Codex's items 2 are already done.

2. **On the `textual` question** (which the King said to skip for now): `uv tool install kingdom-cli` won't install `textual` since it's in a `dependency-groups` section, not `[project.optional-dependencies]`. If you wanted to support `uv tool install kingdom-cli[chat]`, you'd need to move it to `[project.optional-dependencies]`. But that's a separate ticket.

3. **What's actually left is just items 3 and 4** — set the GitHub repo description/topics and make sure the version bump lands in the release PR.

Let me set the GitHub repo description now.The repo description and topics are already set. So Codex's items 2 and 3 are already done.

That means the only remaining blocker is item 4: **the version bump needs to be in whatever PR/commit lands on `master`**. Since `pyproject.toml` already has `version = "0.1.1"` (bumped from `0.1.0`), as long as that change makes it to `master`, the release workflow will fire.

Summary of where we are:
- **Done:** LICENSE, README, pyproject metadata (description, license classifier, changelog URL, authors, keywords, classifiers, urls), GitHub repo description + topics, release workflow, changelog categories, publish checklist doc, architecture doc
- **Remaining before merge:** run final validation (`uv build` + `twine check` + `pytest`) on the current branch, then merge to `master` with the version bump

Want me to run the final validation now?
