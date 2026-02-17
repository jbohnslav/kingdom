---
from: codex
to: king
timestamp: 2026-02-17T01:05:02Z
---

I’ll quickly inspect `pyproject.toml` and the CI workflow to see where `textual` is declared and how `uv sync` is invoked, then I’ll propose the minimal command change.
I found `textual` under the `chat` dependency group in `pyproject.toml`, and CI currently runs plain `uv sync`. I’m opening the workflow now to suggest the exact line change.
Change it in `.github/workflows/ci.yml:20`.

`textual` is in `pyproject.toml` under `[dependency-groups].chat` (`pyproject.toml:24-26`), and CI currently does plain `uv sync`, which won’t bring that group in.

Recommended CI install line:

```yaml
- name: Install dependencies
  run: uv sync --group chat
```

If you want to prevent this class of miss going forward, use:

```yaml
run: uv sync --all-groups
```

I’d pick `--group chat` as the minimal fix, unless you explicitly want CI to validate every dependency group.
