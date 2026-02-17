---
from: codex
to: king
timestamp: 2026-02-17T11:01:16Z
---

I’m going to quickly check the current `pyproject.toml` package name and the new release workflow so I can give the King the exact next steps without guessing.
I confirmed the repo still has `name = "kingdom"`. I’ll also quickly verify PyPI name availability so we can recommend a concrete name now.
I checked the repo and PyPI directly.

- `pyproject.toml` still has `name = "kingdom"`.
- PyPI status right now:
  - `kingdom`: taken
  - `kingdom-cli`: available
  - `kd-cli`: available

I’d pick `kingdom-cli` for discoverability, keep the `kd` command as-is.

Then the first release is:

1. Change `[project].name` to `kingdom-cli` and bump `version` (must bump, or your workflow will skip publish).
2. Merge to `master`.
3. In PyPI: `Account settings -> Publishing -> Add pending publisher` with:
   - Project name: `kingdom-cli`
   - Owner: `jbohnslav`
   - Repository: `kingdom`
   - Workflow: `release.yml`
   - Environment: blank
4. Push/merge the bump commit; your existing `release.yml` will build, create GitHub Release notes, and publish.

If you want, I can make the `pyproject.toml` change now (name + next version) in one commit-ready patch.
