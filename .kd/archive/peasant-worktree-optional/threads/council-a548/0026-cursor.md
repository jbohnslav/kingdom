---
from: cursor
to: king
timestamp: 2026-02-13T14:00:07Z
---

The current approach to strip `CLAUDECODE` is **correct and necessary** to prevent "nested session" errors when `kd` is run from within Claude Code.

### Analysis

1.  **Correctness:**
    *   The `claude` CLI checks for the `CLAUDECODE` environment variable to prevent accidental recursion (a "session within a session"), which can cause resource conflicts or infinite loops.
    *   Since `kd` launches independent background agents ("peasants" or "council members"), these are *intended* to be separate sessions. Stripping the variable effectively tells the child `claude` process "you are the root session," which is the desired behavior.

2.  **Coverage:**
    *   You correctly applied this to both:
        *   `launch_work_background` (for `kd peasant start` and `kd peasant review --reject`)
        *   `council_ask` (for `kd council ask`)
    *   This covers all asynchronous agent launches.

3.  **Other Variables:**
    *   **Do NOT strip:** `ANTHROPIC_API_KEY` (needed for auth), `PATH` (needed to find tools), or standard system variables.
    *   **Edge Cases:**
        *   **Windows:** Environment variables are case-insensitive on Windows, but Python's `os.environ` keys are usually normalized. The check `k != "CLAUDECODE"` is generally safe, but `k.upper() != "CLAUDECODE"` would be strictly more robust on Windows. However, given the context (likely POSIX-centric dev environment), the current check is acceptable.
        *   **Missing Variable:** The dict comprehension `{k: v for k, v in os.environ.items() if k != "CLAUDECODE"}` handles the case where `CLAUDECODE` is missing perfectly fine (it just copies everything).

### Recommendation

The implementation is solid. No changes are needed.

If you prefer a slightly more idiomatic Python style (which avoids iterating the whole dict if you only want to remove one key), you could use:

```python
worker_env = os.environ.copy()
worker_env.pop("CLAUDECODE", None)
```

But your current list comprehension is functionally equivalent and correct.

**Verdict:** ✅ The fix is approved.
