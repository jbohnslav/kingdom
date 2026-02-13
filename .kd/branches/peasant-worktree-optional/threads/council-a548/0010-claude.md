---
from: claude
to: king
timestamp: 2026-02-13T12:51:28Z
---

**Yes, the worker correctly saves sessions** (line 53: `c.save_sessions(args.base, args.feature)`). And it loads them on startup (line 40). So session resume IDs survive across async dispatches.

## Summary

The async council launch looks correct. The flow is:

```
council ask "question"
  → write king message to thread
  → Popen worker subprocess (detached)
  → fall through to council_watch() which polls for response files
  → worker runs agents, writes responses as thread message files
  → watch sees new files, renders panels
  → worker saves sessions on exit
```

**Two minor things that aren't bugs but worth noting:**

1. **`--sync` mode duplicates the `save_sessions` call** that the worker handles in default mode. In `--sync`, sessions are saved in-process (line ~399 area). In default mode, the worker saves them. This is correct — they're different code paths.

2. **The worker's `--timeout` default is still `120`** (worker.py:31) while the CLI now defaults to `300` (cli.py:284). The CLI passes `--timeout` explicitly to the worker command, so the worker's argparse default is never used in practice — but it's a stale value that could confuse someone reading the worker in isolation. Trivial to fix.

The design is sound — the `Popen` + file-polling pattern avoids the old problem where blocking in-process meant TUI hosts (like Cursor) couldn't return control to the user.
