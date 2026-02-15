---
from: codex
to: king
timestamp: 2026-02-15T02:52:37Z
---

Using the `kingdom` skill again for this ticket-audit pass. I’ll run `kd tk list`, then open every currently open ticket and check if the revisions now match the design cleanly.
Yes, this is much better. You fixed most of the big mismatches.

**What you got right**
1. `3e60` is now correctly scoped to Phase 2 only.
2. `70f6` now subsumes `d09d` cleanly (turn pagination + visual separation in one ticket).
3. `6412` now explicitly includes live stream visibility in `watch_thread()`.
4. `a9c9` now has stronger “concrete metadata” language instead of vague “logs and/or state.”
5. `e756` now clearly defines shared stream extraction for both CLI and TUI.

**What’s still off**
1. **Phase 3 still has no ticket.**
- Design still includes group chat auto-mode, but there’s no open ticket for it.
- Recommendation: add a dedicated Phase 3 orchestration ticket (round-robin engine, interrupt behavior, stop conditions, tests).

2. **Config schema work is still not explicitly ticketed.**
- `council.chat` and `council.auto_commit` are required by design/tickets, but current schema only supports `council.members` + `council.timeout` (`src/kingdom/config.py`).
- Recommendation: add a ticket for config dataclass/validation/schema updates.

3. **`a9c9` title includes timed out/stopped, but AC doesn’t require `timed_out` explicitly anymore.**
- Right now AC says “responded, running, errored/interrupted, pending.”
- Recommendation: either add explicit `timed_out` state to AC, or retitle ticket to match reduced scope.

4. **`a4f5` errored detection is brittle.**
- AC says detect errored via message body prefix (e.g. `"Error:"`), but actual formatting can vary (`*Error: ...*`, markdown wrappers).
- Recommendation: specify a robust rule (normalized prefix/regex) or explicit metadata source.

5. **`1e3d` is still high-risk vs project goal.**
- It adds side effects and failure modes unrelated to “make council feel alive.”
- Recommendation: either defer it until after `e756/6412/a9c9/3e60`, or set default `council.auto_commit` to `false` initially.

**Simpler implementation path**
1. Do `e756` first (stream-json + parsers + extractor).
2. Then `6412` + `a9c9` (reliability + status visibility).
3. Then `70f6` + `a4f5` (readability).
4. Then `3e60` (TUI Phase 2).
5. Leave `1e3d` and Phase 3 auto-mode for last.

If you apply those 4-5 adjustments, the ticket plan will be tight and execution-friendly.
