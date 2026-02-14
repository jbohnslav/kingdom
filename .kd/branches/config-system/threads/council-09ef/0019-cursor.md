---
from: cursor
to: king
timestamp: 2026-02-14T15:58:17Z
---

Here is the analysis and recommendation for fixing the reported bugs.

### Analysis

**Bug 1: `timeout=None` passed to `member.query()`**
The diagnosis is correct. The CLI argument `timeout` defaults to `None`. When passed to `member.query(prompt, timeout)`, it overrides the default `600` with `None`, causing the `TypeError` in the comparison `time.monotonic() - start > timeout`. It also breaks the `timeout + 30` calculation in the async watch path.

**Bug 2: Status role logic inverted**
The diagnosis is correct based on the `clean_agent_env` logic.
*   **Context**: `clean_agent_env` explicitly strips `CLAUDECODE` when spawning agents.
*   **Implication**:
    *   **King (User)**: Runs in the main Claude Code session $\rightarrow$ `CLAUDECODE` is present.
    *   **Hand/Peasant (Agent)**: Runs in a subprocess with stripped env $\rightarrow$ `CLAUDECODE` is missing.
*   **Current Logic**: `role = 'hand' if CLAUDECODE else 'king'` incorrectly identifies the User (who has the env var) as 'hand'.
*   **Fix**: Swap to `role = 'king' if CLAUDECODE else 'hand'`.

---

### Recommendations

#### Fix for Bug 1 (Timeout)

Adopt **Option C (Resolve Early)**. It is the most robust because it guarantees `timeout` is a valid integer for the entire scope of the function, fixing both the synchronous `query()` call and the asynchronous `watch_thread()` calculation in one place.

**Plan**:
In `src/kingdom/cli.py` inside `council_ask`:
1.  Locate the block where `c` (Council) is created.
2.  After `if timeout is not None: c.timeout = timeout`, add `timeout = c.timeout`.
3.  This ensures `timeout` holds the effective integer value (either the user override or the config default) for the rest of the function.

#### Fix for Bug 2 (Role Inversion)

Swap the ternary values in `src/kingdom/cli.py`. This appears in two places: `status` command and `whoami` command.

**Plan**:
In `src/kingdom/cli.py`:
1.  Find `role = "hand" if os.environ.get("CLAUDECODE") else "king"`.
2.  Change to `role = "king" if os.environ.get("CLAUDECODE") else "hand"`.

These changes will resolve the 5 test failures.
