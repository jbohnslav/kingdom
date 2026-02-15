---
from: codex
to: king
timestamp: 2026-02-15T19:39:10Z
---

Using the `kingdom` skill for this review because this is a `kd design` quality check. I’ll read the updated design doc and re-validate the key assumptions against current code/config behavior before giving a second-pass gap list.
I’ve loaded the revised design; next I’m validating a few concrete claims (dependency group, config/schema additions, and command surface) against the repo so the remaining feedback is precise.
I found a few additional structural risks (especially around concurrent streaming files and interrupt semantics). I’m verifying whether council workers currently record PIDs, since that affects whether your Escape-interrupt plan is actually implementable.
Much better. The revised doc fixed most of the big issues from my first pass. A few important gaps are still open:

1. Concurrent streaming is still underspecified and one claim is incorrect.
` .kd/branches/kd-chat/design.md:238` says concurrent use needs no special handling, but stream files are shared per member (`.stream-{member}.jsonl`) and are deleted on completion/retry (`src/kingdom/council/council.py:112`, `src/kingdom/council/council.py:128`, `src/kingdom/council/base.py:123`).
Recommendation: decide a unique stream file key per request/turn (not just per member).

2. Interrupt semantics are not fully implementable as written yet.
You plan Escape to kill active agents (`.kd/branches/kd-chat/design.md:62`, `.kd/branches/kd-chat/design.md:93`), but council code does not persist PIDs and only saves `resume_id` (`src/kingdom/council/council.py:155`), and `query_once()` keeps `Popen` internal (`src/kingdom/council/base.py:137`).
Recommendation: explicitly scope interrupt to “queries launched by this `kd chat` process” vs “any in-flight thread work,” then design to that scope.

3. There is a design contradiction on state.
You say no state lives only in TUI (`.kd/branches/kd-chat/design.md:83`), but `/mute` is session-scoped and resets on close (`.kd/branches/kd-chat/design.md:66`).
Recommendation: explicitly allow ephemeral UI/session state, while keeping conversation truth in thread files.

4. Config schema changes are still not fully specified.
Doc now depends on `council.chat` and `council.preamble` (`.kd/branches/kd-chat/design.md:132`, `.kd/branches/kd-chat/design.md:147`), but current schema only allows `members`/`timeout` (`src/kingdom/config.py:98`, `src/kingdom/config.py:174`).
Recommendation: define exact JSON shape/defaults/validation behavior upfront (including unknown-key behavior and migration expectations).

5. Round inference by message ordering alone is fragile in edge cases.
You chose inference (`.kd/branches/kd-chat/design.md:141`), but expected responders currently come from thread members and latest king ask semantics (`src/kingdom/thread.py:383`, `src/kingdom/thread.py:389`).
Recommendation: decide how rounds behave with `@member`, `/mute`, retries, errors/timeouts, and concurrent writers. If inference gets messy, add minimal persisted turn metadata.

6. “Per-agent preamble override” wording is off.
Doc says `agents.<name>.prompts.council` can override preamble (`.kd/branches/kd-chat/design.md:149`), but that field is currently additive phase prompt, not preamble override (`src/kingdom/council/base.py:68`).
Recommendation: either keep it additive, or introduce a true per-agent preamble key.

7. Minor doc cleanup:
`What does NOT exist yet` still lists Textual dependency while also saying it was added (`.kd/branches/kd-chat/design.md:39`, `pyproject.toml:22`).

If you lock these 6 design decisions before breakdown, the implementation plan is solid.
