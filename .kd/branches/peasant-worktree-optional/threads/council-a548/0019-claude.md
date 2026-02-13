---
from: claude
to: king
timestamp: 2026-02-13T13:08:29Z
---

Here's my review of the implementation against the design doc.

## Review: `kd work` Implementation

### What matches the design

**The core `kd work` command (cli.py:1666-1723)** — correctly implemented:
- Top-level command `@app.command("work")`, not hidden under `agent`
- Ticket ID is a positional argument
- `--worktree`, `--thread`, `--session` are optional — when omitted (interactive/foreground mode), it auto-resolves: `worktree=cwd`, `session=hand-{ticket}`, `thread={ticket}-work`
- Creates the thread if it doesn't exist
- Delegates to `run_agent_loop` — the harness is unchanged and agnostic
- Exits non-zero if status != done

**`peasant start` refactored (cli.py:1010-1102)** — now builds a `kd work` command instead of `kd agent run`:
- Uses `python -m kingdom.cli work` as the subprocess
- Passes all args explicitly (`--worktree`, `--thread`, `--session`, `--base`)
- `--hand` flag correctly sets `worktree_path = base`
- Old `launch_harness` helper deleted, inline Popen — fine

**`peasant review --reject` relaunch (cli.py:1527-1579)** — updated to launch via `kd work` too, with a hand-mode fallback (checks if worktree exists, falls back to `base`).

**`launch_harness` removed** — no longer exists. The old `agent_run` command is gone from the CLI.

**Council preamble (base.py)** — separate change, not part of the design, but sensible. Adds a read-only system prompt to council queries.

### Issues found

**1. Tests are broken — 3 tests reference the deleted `launch_harness`**

`tests/test_cli_peasant.py` lines 802, 840, 862 still do:
```python
with patch("kingdom.cli.launch_harness", return_value=54321) as mock_launch:
```
This raises `AttributeError` since `launch_harness` no longer exists. These tests need to be updated to mock `subprocess.Popen` instead (matching what the code actually does now).

**2. Duplicated Popen boilerplate — `peasant start` and `peasant review --reject`**

The ~25-line Popen block (build cmd list, open fds, Popen, close fds) is copy-pasted in both `peasant_start` and `peasant_review`. The old code had `launch_harness` as a helper for exactly this reason. Deleting the helper was correct (per the design — `peasant start` should invoke `kd work`), but the duplication should be extracted into a small helper like `launch_work_background(base, feature, session_name, agent, ticket_id, worktree, thread_id) -> pid`.

**3. `harness.py:main()` is now dead code**

`harness.py:452-489` still has a `main()` entry point with `argparse` for the old `kd agent run` interface. The `__main__` block at line 488 still references it. Since `peasant start` now invokes `kd work` (via `kingdom.cli`), nothing calls `python -m kingdom.harness` anymore. This should be cleaned up — the docstring at the top still says `kd agent run` too.

**4. The `agent` typer app is now empty**

Lines 1662-1663 still register `agent_app = typer.Typer(...)` and `app.add_typer(agent_app, name="agent")`, but `agent_run` was the only command in it. So `kd agent` is now an empty subcommand group. Should be removed.

**5. No session seeding in interactive `kd work`**

When `kd work` is run interactively (foreground), it creates the thread and auto-names the session `hand-{ticket}`, but it doesn't seed the thread with the ticket content (the way `peasant start` does at lines 1053-1063). So the first harness iteration would have no context in the thread about what the ticket contains. The harness reads the ticket file directly via `build_prompt`, so this isn't a functional bug — but the work thread will be missing the initial seed message, which means `kd peasant read` won't show the ticket body.

### Summary

| Aspect | Status |
|--------|--------|
| `kd work` command | Correct per design |
| `peasant start` delegation | Correct per design |
| `--hand` flag | Correct per design |
| Interactive mode (auto-resolve) | Works, minor gap (no seed msg) |
| Tests | **Broken** — 3 tests reference deleted `launch_harness` |
| Dead code | `harness.py:main()`, empty `agent` subcommand |
| DRY | Popen block duplicated in two places |

The architecture is right. The main action item is fixing the 3 broken tests.
