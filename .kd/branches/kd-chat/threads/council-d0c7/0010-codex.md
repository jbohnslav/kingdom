---
from: codex
to: king
timestamp: 2026-02-16T18:26:54Z
---

Yes, your interpretation matches the King’s intent.

The key mismatch today is exactly what he complained about: current behavior does `broadcast + extra sequential turns` on the same king prompt, which over-produces messages.

Recommended spec to lock in:

1. King turn 1 (or explicit `@all`): one broadcast round only, then stop and wait for king.
2. Later king turns (default): sequential round-robin only, capped by `N` total councillor messages, then stop.
3. `@member` sets who speaks next (priority override), then normal round-robin resumes.
4. `@all` on a follow-up forces broadcast mode for that turn.
5. Budget is per king turn, in messages (not rounds).

Direct answers:

1. Does this match intent?
Yes.

2. N default?
Default `N = number_of_active_members` (unmuted) is best. It gives “each speaks once” and avoids spam. Advanced users can raise it.

3. First-message vs follow-up distinction?
Infer from thread history, not new persisted state. If this is the first king message in thread (or `@all`), broadcast; otherwise follow-up mode.

4. Concerns on `@mention` override?
Main one is parsing ambiguity. Define strict rules now:
- Only parse plain `@name` tokens.
- Use first valid mention only.
- Ignore mentions inside code fences/quotes if possible.
- Ignore unknown/muted names.
- Mention override should not bypass message budget.

5. Simplest path with current `run_chat_round()`?
Keep single coordinator. Change its mode selection per king turn:
- Determine turn mode (`broadcast_once` vs `round_robin_budgeted`).
- Remove “auto rounds after broadcast.”
- Add a per-turn `remaining_messages` counter.
- In sequential path, pick next speaker from queue + optional mention override after each finalized response.

One important design decision to make now: whether failed/time-out attempts consume budget. I recommend “yes, attempts consume budget” for predictability and to prevent infinite churn.
