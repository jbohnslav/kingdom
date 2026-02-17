---
from: codex
to: king
timestamp: 2026-02-17T13:07:27Z
---

I agree with Claude: ship the whole thing for `0.1.1`.

- `kd chat` is in the main workflow, so making `textual` optional right now creates first-run friction.
- `textual` is not heavy enough to justify split complexity at launch.
- The split adds ongoing burden: dual install docs, dual test matrix, extra support/debug paths.

Practical call: make `textual` a normal runtime dependency now, launch, and revisit only if users explicitly ask for a “headless/minimal” install.
If that signal appears, then move chat to an extra (`kingdom-cli[chat]`) with a clean fallback path.
