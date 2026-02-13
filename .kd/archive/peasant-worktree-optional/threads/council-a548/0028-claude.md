---
from: claude
to: king
timestamp: 2026-02-13T14:01:56Z
---

OK, I now have the full picture. Here's my analysis.

## Review: `CLAUDECODE` Environment Variable Stripping

### The problem being solved

When `kd` is run from inside a Claude Code session (which is the primary use case — the King tells their Hand to run `kd council ask ...` or `kd peasant start ...`), the `CLAUDECODE=1` env var is set. Child `claude` processes inherit this, and Claude Code [sets this variable since v0.2.47](https://github.com/anthropics/claude-code/issues/531) to let scripts detect they're running inside Claude. The concern is that child `claude --print` invocations may behave differently or refuse to start when they see this variable.

### What the current code does

`CLAUDECODE` is stripped in exactly **two** places:

1. **`council_ask` → council worker Popen** (line 423): strips before spawning `python -m kingdom.council.worker`
2. **`launch_work_background`** (line 1048): strips before spawning `kd work`

### Where the stripping is **missing**

This is the critical gap. Stripping it from the *intermediate* Python subprocess is necessary but not sufficient. The `claude` CLI is ultimately called from two places, and **neither strips the env**:

1. **`harness.py:324` — `subprocess.run(cmd, ...)`** — the harness calls `claude --print` directly. No `env` kwarg. If `kd work` is launched interactively (foreground, no `launch_work_background` wrapper), it inherits `CLAUDECODE` from the parent.

2. **`council/base.py:69` — `subprocess.run(command, ...)`** in `CouncilMember.query()`. No `env` kwarg. This is the code path used by the `--sync` flag and also by the **worker subprocess itself** (the worker calls `c.query_to_thread(...)` which calls `member.query()` which calls `subprocess.run`). So even though you stripped `CLAUDECODE` before spawning the worker, the worker inherits a clean env, and then `member.query()` passes it through — that part works by accident because the worker *did* get a clean env. But `--sync` mode calls `member.query()` directly from the parent process where `CLAUDECODE` is still set.

**Summary of coverage:**

| Code path | `CLAUDECODE` stripped? |
|---|---|
| `council ask` (default async) → worker Popen | Yes (line 423) |
| Worker → `member.query()` → `subprocess.run(claude ...)` | Yes (inherited clean env) |
| `council ask --sync` → `member.query()` → `subprocess.run(claude ...)` | **No** |
| `peasant start` → `launch_work_background` → `kd work` | Yes (line 1048) |
| `kd work` (background) → harness → `subprocess.run(claude ...)` | Yes (inherited clean env) |
| `kd work` (interactive/foreground) → harness → `subprocess.run(claude ...)` | **No** |

### Recommendation: strip at the leaf, not the branches

Rather than playing whack-a-mole at every Popen site, strip `CLAUDECODE` at the two places that actually call the `claude`/`codex`/`cursor` CLI:

- **`harness.py:324`** — add `env={k: v for k, v in os.environ.items() if k != "CLAUDECODE"}` to the `subprocess.run` call
- **`council/base.py:69`** — same

Then you can **remove** the stripping from `launch_work_background` and the council worker Popen — those are just spawning Python subprocesses that don't care about `CLAUDECODE`. The leaf calls to the actual agent CLIs are what matter.

Even better, centralize it:

```python
# In agent.py or a shared util
def clean_agent_env() -> dict[str, str]:
    """Return env dict safe for spawning agent CLI subprocesses."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
```

Then use it in both leaf call sites. One definition, impossible to miss.

### Are there other env vars to strip?

Based on my research, `CLAUDECODE` is the only one Claude Code sets for detection purposes. However, there are a few things to consider:

- **`CLAUDE_CODE_SHELL`** — overrides shell detection. Probably harmless to pass through, but worth being aware of.
- **`ANTHROPIC_API_KEY`** — if set, it's *needed* by child `claude` processes. Don't strip it.
- **`CLAUDE_CODE_EXPERIMENTAL_*`** / **`CLAUDE_CODE_DISABLE_*`** — feature flags that might affect child behavior. These could go either way — the child agent probably *should* inherit the same experimental settings. I'd leave them alone.

So `CLAUDECODE` is the right (and only) var to strip. The issue isn't *what* you're stripping, it's *where*.

### Edge case: non-Claude backends

The stripping is harmless for Codex and Cursor — they don't check `CLAUDECODE`. But centralizing it in `clean_agent_env()` makes it clear this is about agent subprocess hygiene, not Claude-specific logic.
