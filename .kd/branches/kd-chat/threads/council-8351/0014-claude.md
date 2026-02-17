---
from: claude
to: king
timestamp: 2026-02-16T19:01:56Z
---



I can see codex's full message. Here's their proposal:

1. **Spec/doc sync first** (quick) — update the design doc and ticket 3b76 wording to match actual behavior (follow-up = sequential only, no broadcast). They noted `kd design show` still references the old `auto_rounds` behavior in multiple sections.

2. **0f27 first** (cross-talk/session isolation) — they agree it's the highest correctness risk and argue it should come before a6a6, because if isolation is wrong, results from a6a6/7397 testing could be misleading.

3. **a6a6 next** — clear the xfails, manual TUI verification.

4. **7397** — thinking tokens, UX polish, after streaming is stable.

5. **cf1a** — integration tests after behavior settles.

6. **8461** — parked (blocked).
