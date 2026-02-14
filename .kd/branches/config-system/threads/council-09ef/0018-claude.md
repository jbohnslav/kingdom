---
from: claude
to: king
timestamp: 2026-02-14T15:58:04Z
---

Confirmed. Here's my assessment.

---

### Bug 1: timeout=None — Option C is correct

You're right that Option C is the cleanest. The three options compared:

| Option | Fix location | Fixes all call sites | Keeps type safety downstream |
|--------|-------------|---------------------|------------------------------|
| A) `timeout or c.timeout` at call sites | Lines 403, 467, 483 | Must patch 3 places | Yes |
| B) Guard in `query()` method | `base.py:120` | Yes | No — `timeout` stays `int | None` throughout |
| C) Resolve early in `council_ask` | Once, near line 321 | Yes | Yes — downstream always sees `int` |

Option C is clearly best. Resolve `None` to `c.timeout` (which itself comes from config) once, right after the council is created. Something like:

```python
effective_timeout = timeout if timeout is not None else c.timeout
```

Then use `effective_timeout` everywhere. This also aligns with the config design's "CLI flags override config" principle — the `--timeout` flag is either provided (use it) or not (fall back to config/default).

One subtlety: don't use `timeout or c.timeout`. If someone passes `--timeout 0` for some reason, `0 or 600` gives `600`. Use `timeout if timeout is not None else c.timeout`.

### Bug 2: role logic inverted — straightforward swap

The fix is:

```python
role = "king" if os.environ.get("CLAUDECODE") else "hand"
```

At both lines 1898 and 2080. The reasoning: `CLAUDECODE` is set when running inside Claude Code, which is the human operator's environment — the king. When it's absent, you're an agent (hand/peasant), and "hand" is the correct fallback for an unidentified agent.

Both fixes are small and isolated. No architectural concerns.
