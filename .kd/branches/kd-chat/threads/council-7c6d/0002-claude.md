---
from: claude
to: king
timestamp: 2026-02-17T01:04:46Z
---

Looking at this, `textual` is likely in an optional dependency group (like `[dev]` or `[tui]`) that isn't being installed in CI.

Let me check what we're working with.There it is. `textual` is in the `chat` dependency group (line 24), but CI only runs `uv sync` (line 20 of ci.yml), which installs the default `dev` group but **not** `chat`.

The fix is straightforward — change the CI command from:

```
uv sync
```

to:

```
uv sync --group chat
```

This tells uv to install both the default `dev` group and the `chat` group. That's in `.github/workflows/ci.yml`, line 20.

Alternatively, if we think `textual` should always be installed for development, we could move it into the `dev` dependency group instead of having a separate `chat` group. But that's a design decision — keeping it in a separate group makes sense if some contributors don't need the TUI dependencies locally.
