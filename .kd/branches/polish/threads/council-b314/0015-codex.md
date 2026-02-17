---
from: codex
to: king
timestamp: 2026-02-17T11:02:16Z
---

I’m applying this now: I’ll update `pyproject.toml` to `name = "kingdom-cli"` and bump the version, then run checks to confirm the release workflow will pick it up.
I found `pyproject.toml` at `name = "kingdom"` and `version = "0.1.0"`. I’m editing that file now to set the package name to `kingdom-cli` and bump to `0.1.1`.
I’ve made the file change and confirmed the diff. Next I’m running a quick `uv build` to ensure the renamed package metadata still builds cleanly.
Updated as requested:

- `pyproject.toml:2` -> `name = "kingdom-cli"`
- `pyproject.toml:3` -> `version = "0.1.1"`

Validation:

- Ran `uv build` successfully; artifacts built as `kingdom_cli-0.1.1` (`.tar.gz` and `.whl`).

Next release step is unchanged: add the PyPI pending publisher for project `kingdom-cli`, then merge the bump commit to `master` so `release.yml` can publish automatically.
