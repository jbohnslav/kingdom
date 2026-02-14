---
from: codex
to: king
timestamp: 2026-02-14T15:58:55Z
---

Using the `kingdom` skill for this debugging review. I’ll verify the cited call paths in `cli.py`/`council/base.py` and then give a concrete recommendation for Bug 1 and Bug 2, with tradeoffs.
I verified your diagnosis: both bugs are real in current code. I’ll quickly inspect `Council.create` timeout behavior so I can confirm the safest “resolve early” pattern for Bug 1.
`Council.create()` confirms `c.timeout` already carries config/default timeout, so an early `effective_timeout` is the right single source. I’ll sanity-check tests around role semantics (`CLAUDECODE`) to confirm the intended `king`/`hand` behavior before final recommendation.
I found one nuance on Bug 2: local tests currently encode `whoami` behavior as `CLAUDECODE => hand`, so flipping both sites may create a behavior mismatch. I’ll check docs/usages quickly so the recommendation aligns with intended product semantics, not just one failing test.
Your diagnosis on Bug 1 is correct, and Option C is the best primary fix.

**Bug 1 recommendation (`timeout=None`)**
- Normalize once in `council_ask` and use that value everywhere.
- In practice, since `c.timeout` is already config/default-aware from `Council.create()` (`src/kingdom/council/council.py:57`) and optionally overridden by CLI (`src/kingdom/cli.py:342-343`), the cleanest pattern is:
  - treat `c.timeout` as the canonical effective timeout
  - replace all targeted/sync/async/watch callsites to use `c.timeout`
- This fixes all current failure paths at once:
  - targeted query calls at `src/kingdom/cli.py:403` and `src/kingdom/cli.py:483`
  - async watch math at `src/kingdom/cli.py:467`
- Avoid Option A as written (`timeout or c.timeout`) because `0` is falsy; use explicit `is not None` logic if you keep a local variable.

**Hardening suggestion (optional but good)**
- Add a defensive guard in `CouncilMember.query` (`src/kingdom/council/base.py:119-120`) so `None` can’t crash even if a future callsite regresses.
- I’d still do C first; B is defensive backup.

**Bug 2 recommendation (`CLAUDECODE` role)**
- You’ve found a real semantic inconsistency risk, but there’s one caveat:
  - current `whoami` tests in repo encode `CLAUDECODE => hand` (`tests/test_cli_whoami.py:23-29`)
  - status JSON expectation is `king` by default (`tests/test_cli_status.py:59-72`)
- So before flipping both `src/kingdom/cli.py:1898` and `src/kingdom/cli.py:2080`, decide intended product rule:
  1. `CLAUDECODE => king` everywhere (your proposal), or
  2. `status` defaults to `king` unless `KD_ROLE` is set, while `whoami` remains environment-introspection-oriented.
- If you want minimal change to fix the reported single failing status test without broader behavior churn, adjust status logic first.
- If you want conceptual consistency with your current statement, flip both and update whoami expectations accordingly.

If you want, I can do a quick “expected blast radius” map for each Bug 2 policy choice before implementation.
