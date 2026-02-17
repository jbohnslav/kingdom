---
from: cursor
to: king
timestamp: 2026-02-17T01:04:59Z
---

I'll investigate the dependency configuration and CI workflow to pinpoint why `textual` is missing.

First, I'll check `pyproject.toml` to see how `textual` is defined (main dependency or optional group).

The issue is that `textual` is defined in the `chat` dependency group in `pyproject.toml`, but the default `uv sync` command in CI only installs the project dependencies and the `dev` group.

We need to update the CI workflow to install all dependency groups.

I will update `.github/workflows/ci.yml` to use `uv sync --all-groups`.

The issue is that `textual` is listed in the `chat` dependency group in `pyproject.toml`, but `uv sync` by default only installs the main project dependencies and the `dev` group (if configured).

I've updated the CI workflow to install all dependency groups.

Here are the changes:

```yaml:19:20:.github/workflows/ci.yml
      - name: Install dependencies
        run: uv sync --all-groups
```

This ensures that dependencies from the `chat` group (like `textual`) are available during the test run.
