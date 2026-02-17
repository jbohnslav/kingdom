---
from: claude
to: king
timestamp: 2026-02-17T11:00:33Z
---

The easiest way is to use PyPI's "pending publisher" flow — you set up trusted publishing *before* the first publish, and the first workflow run creates the package automatically.

1. Go to https://pypi.org/manage/account/publishing/
2. Scroll to **"Add a new pending publisher"**
3. Fill in:
   - **PyPI project name:** `kingdom` (or whatever name you want — check availability first)
   - **Owner:** `jbohnslav`
   - **Repository:** `kingdom`
   - **Workflow name:** `release.yml`
   - **Environment:** leave blank
4. Click **Add**

That's it. Next time the workflow runs and calls `pypa/gh-action-pypi-publish`, PyPI will automatically create the package and associate it with your account. No API tokens, no manual `twine upload`.

One heads up — `kingdom` is almost certainly taken on PyPI. Let me check.As expected — `kingdom` is taken. Both `kingdom-cli` and `kd-cli` are available.

You'll need to pick a PyPI package name. The name in `pyproject.toml` under `[project] name` is what gets published. This is independent of the `kd` console script entry point — users will still run `kd` regardless. Let me check what you have now.You'll need to change `name = "kingdom"` to something available. Options:

- **`kingdom-cli`** — clear, matches the GitHub repo concept
- **`kd-cli`** — matches the command name users actually type

Either way, `pip install kingdom-cli` (or `kd-cli`) would give users the `kd` command. Your call on which name you prefer — want me to update `pyproject.toml` once you pick one?
