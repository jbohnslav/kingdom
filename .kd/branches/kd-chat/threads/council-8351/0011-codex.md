---
from: codex
to: king
timestamp: 2026-02-16T19:00:21Z
---

I’m pulling the current branch design and ticket readiness now so I can give a concrete next-step order, not just a guess.
I found one important mismatch: the approved design still describes the old `auto_rounds` behavior, so we should account for a docs/spec sync step in “what’s next.” I’m quickly checking each open branch ticket details to propose a concrete execution order.
Next should be:

1. `Spec/doc sync first` (quick): update the approved design + ticket wording to match the intended behavior (`follow-up = sequential only`, no automatic follow-up broadcast).
`kd design show` is still describing old `auto_rounds` behavior in multiple sections.

2. `Start 0f27` immediately: this is the highest correctness risk (session/context cross-talk). If isolation is wrong, results from `a6a6`/`7397` can be misleading.

3. `Finish a6a6` next: clear the two xfail regressions and do the manual TUI verification AC so it can be closed cleanly.

4. `Do 7397` after streaming correctness is stable: thinking-token rendering is UX polish, lower risk.

5. `cf1a` after behavior settles: integration tests are valuable, but they should lock in stable semantics (especially post-`0f27`).

6. `8461` stays parked (blocked on `8ea4`, P3).

I agree with Claude that `a6a6` is close, but I’d prioritize `0f27` first because it’s a correctness/isolation issue, not just output quality.
