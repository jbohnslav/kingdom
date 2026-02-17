---
from: claude
to: king
timestamp: 2026-02-17T03:59:33Z
---

Looking at this summary, the approach was clean — surgical restoration using `git checkout` from the parent of the removal commits, which is the safest way to get exact pre-removal state for files that hadn't been modified since.

The key distinction here is solid: **restore the cursor backend capability** (parsers, builders, stream handling, config validation, tests) while **keeping the architectural simplifications** that were made alongside the removal (no default agent, simplified concat path, unified poll logic).

A few things I'd want to verify:

1. **Tests passing** — the `make_config` fixup for cursor not being in `DEFAULT_AGENTS` is the kind of thing that can have subtle knock-on effects. Have we run the full suite?

2. **Config validation** — cursor is back in `VALID_BACKENDS` but not in `DEFAULT_AGENTS`. That means someone can explicitly configure a cursor agent and it'll work, but `kd` won't create one by default. That's the right behavior — it's an opt-in backend.

3. **The staged vs unstaged split** in the git status caught my eye — `test_agent.py` and `test_tui_poll.py` show `MM` (staged + further unstaged changes). Were there manual fixups on top of the checkout restoration? If so, we should make sure everything's staged consistently before committing.

Want me to look at the actual diffs to verify the restoration is complete and consistent?
