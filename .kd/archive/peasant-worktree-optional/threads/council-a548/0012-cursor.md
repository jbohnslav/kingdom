---
from: cursor
to: king
timestamp: 2026-02-13T12:52:31Z
---

Yes, I've checked the unstaged changes in `src/kingdom/cli.py` and `src/kingdom/council/worker.py`.

**Does it correctly launch the council asynchronously?**
**Yes.** The implementation correctly uses `subprocess.Popen` with `start_new_session=True` to launch the worker process in the background.

Here are the details:
1.  **Default Behavior:** `kd council ask` now defaults to asynchronous dispatch. It launches the worker process and then immediately starts watching the thread (polling for responses) in the foreground.
2.  **Detached Process:** The worker is launched with `start_new_session=True` and `stdin/stdout/stderr` redirected to `DEVNULL`. This ensures the worker continues running even if the CLI is interrupted (though the CLI watcher would stop displaying updates).
3.  **Worker Script:** The `src/kingdom/council/worker.py` script correctly parses arguments and executes the council query logic in the background process.

**Note on Docstrings:**
I noticed a small inconsistency in the docstring for `council_ask` in `src/kingdom/cli.py`:
-   The docstring mentions: `Use --async to dispatch agents in the background...`
-   But the actual argument is: `no_watch` (flag `--no-watch`).
-   The behavior described for `--async` ("dispatch ... and return immediately") actually corresponds to `--no-watch`. The *default* is now async execution with a foreground watcher.

You might want to update the docstring to match the new flags (`--sync` for blocking, `--no-watch` for fire-and-forget).
