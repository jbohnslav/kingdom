---
from: codex
to: king
timestamp: 2026-02-09T16:39:38Z
---

I’ll read the current design doc and map a concrete interaction model that keeps Claude Code in the driver seat while showing raw council output in one smooth flow.
Use a single user-facing command that is internally two-phase.

You already have the right direction in `design.md` at `.kd/branches/refactor-multi-agent/design.md:247` and `.kd/branches/refactor-multi-agent/design.md:251`. I’d make it explicit:

1. Keep `ask` async and fast.
2. Add a `--wait` mode that automatically does “show second” for you.

Proposed UX:

```bash
kd council ask "Should we use Redis here?" --wait
```

Behavior:
1. Dispatch question to council thread (returns thread id immediately).
2. Then auto-enter the same logic as `kd council show <thread> --wait`.
3. Stream raw member responses as they arrive, no Hand/Claude synthesis.
4. Exit when all expected members replied (or timeout).

That gives one command in Claude Code, while preserving the “King reads raw” rule from `.kd/branches/refactor-multi-agent/design.md:22` and avoiding manual `ask` then `show`.

Minimal command surface:

- `kd council ask "..." --wait` -> interactive one-shot (recommended in TUI)
- `kd council ask "..."` -> fire-and-forget
- `kd council show [thread] --wait` -> reattach later

Implementation note:
- `--wait` should reuse existing `show --wait` renderer, not duplicate logic.
- In `--wait`, print advisor outputs verbatim panels only (no summary layer), so Claude Code is just the terminal host, not mediator.
