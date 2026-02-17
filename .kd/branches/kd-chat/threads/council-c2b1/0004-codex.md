---
from: codex
to: king
timestamp: 2026-02-15T22:54:36Z
---

Using the `kingdom` skill for this ticket-audit pass. I’ll enumerate all tickets with `kd tk list`, then read each one with `kd tk show` and evaluate scope, dependencies, and missing work.
I found 13 open tickets. I’m now reading each `kd tk show` in batches and then I’ll give you a concrete dependency/scope audit with merge/split recommendations.
I’ve finished the first 8 tickets. I’m pulling the remaining 5 now, then I’ll give you a full audit with concrete split/merge/dependency changes.
**Findings**
1. Config model is inconsistent across tickets and likely inconsistent with your design doc.
`8ea4` defines flat keys under `council` (`.kd/branches/kd-chat/tickets/8ea4.md:14`), while your design text has `council.chat.*`. Lock one shape before implementation.

2. There is overlap between `8ea4` and `8461` on preamble ownership.
`8ea4` already adds `preamble` to schema (`.kd/branches/kd-chat/tickets/8ea4.md:18`), and `8461` moves command construction to read `council.preamble` (`.kd/branches/kd-chat/tickets/8461.md:18`). This is workable, but the boundary is blurry and easy to duplicate.

3. Missing ticket for stream-file namespacing / concurrent writers.
Current tickets assume `.stream-{member}.jsonl` as the poll unit (`.kd/branches/kd-chat/tickets/fe84.md:21`), but your design goal includes concurrent `kd chat` + `kd council ask`; without a per-request stream key, collisions/false lifecycle transitions are likely.

4. `3b76` is missing a dependency on config schema work.
It reads `council.auto_rounds` and `council.mode` (`.kd/branches/kd-chat/tickets/3b76.md:14`, `.kd/branches/kd-chat/tickets/3b76.md:28`) but does not depend on `8ea4`.

5. `213e` depends on UI history ticket (`7656`) even though it is logically independent backend logic.
`213e` dep is `7656` (`.kd/branches/kd-chat/tickets/213e.md:4`), which will unnecessarily serialize work.

6. `7656` should probably depend on `fe84` (or narrow scope).
`7656` requires detecting in-flight stream files (`.kd/branches/kd-chat/tickets/7656.md:21`), but polling/detection logic is defined in `fe84`.

7. `16e1` looks too large for one ticket and has a probably-unnecessary dependency on `f9d2`.
It includes keybindings, addressing, dispatch, mute/unmute, help, quit (`.kd/branches/kd-chat/tickets/16e1.md:18`) and currently depends on process-handle infrastructure (`.kd/branches/kd-chat/tickets/16e1.md:4`) even though interrupt behavior is in `d869`.

8. `b71d` under-specs no-current-thread UX vs your stated goal.
It says “prints helpful message” (`.kd/branches/kd-chat/tickets/b71d.md:24`), while your intended UX was to show recent threads and offer create/select.

9. `f9d2` should include PID cleanup acceptance to avoid stale state.
It writes PID (`.kd/branches/kd-chat/tickets/f9d2.md:20`) but does not require clearing PID on completion.

**Dependency fixes**
1. Add `8ea4` as a dependency for `3b76`.
2. Remove `7656` dependency from `213e` (make `213e` independent).
3. Add `fe84` dependency to `7656`, or drop stream detection from `7656` and keep it purely “render existing finalized history.”
4. Remove `f9d2` from `16e1` unless you truly need process handles before basic send/dispatch works.

**Split / Merge recommendations**
1. Split `16e1` into two tickets:
one for send/address/dispatch; one for slash commands + command UX.
2. Either merge `8ea4` + `8461`, or explicitly scope:
`8ea4` = schema only; `8461` = runtime prompt assembly only.

**Missing tickets to add**
1. Stream namespacing for concurrent producers (per request/turn stream files).
2. Explicit session behavior in `kd chat` (whether chat path loads/saves resume IDs, or enforces history-only context).
3. No-current-thread selector UX (recent threads + create flow), if you still want that behavior.

Overall: good structure and sensible phases, but I would fix these dependency/scope edges before starting implementation.
