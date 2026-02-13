---
from: codex
to: king
timestamp: 2026-02-13T12:52:16Z
---

I’m going to inspect the current unstaged diff and trace the `kd council ask --async` path end-to-end, then run the relevant tests to confirm behavior. I’ll report any correctness gaps with exact file/line references.
I’ve confirmed the unstaged changes switch council to async-by-default with a background worker + watcher. Next I’m validating the worker/watch handshake in code and by running the council test suite to see if anything regressed.
I ran the council CLI test file against the unstaged code and it passes. I’m doing one more quick sweep for edge cases (old `--async` compatibility and default-mode behavior) before giving you a yes/no verdict.
Short answer: **yes**, your unstaged council changes do launch async correctly.

What I verified:

- `kd council ask` now starts a detached worker process via `subprocess.Popen(..., start_new_session=True)` in `src/kingdom/cli.py:405`.
- The actual model calls happen in that background worker (`python -m kingdom.council.worker`) in `src/kingdom/council/worker.py:25`.
- Default behavior is now: **dispatch async + watch thread output** (`src/kingdom/cli.py:435`).
- If you want immediate return, `--no-watch` does that (`src/kingdom/cli.py:431`).

Validation:

- `pytest -q tests/test_cli_council.py` -> **28 passed**
- `pytest -q tests/test_cli.py` -> **4 passed**

One important behavior change:

- `--async` is removed; async is now default.
- `--sync` restores old blocking in-process behavior (`src/kingdom/cli.py:371`).
