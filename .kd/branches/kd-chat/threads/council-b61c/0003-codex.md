---
from: codex
to: king
timestamp: 2026-02-16T20:43:36Z
---

I’ll pull up ticket `7397` first so I can answer with specifics about the inconsistent thinking visibility issue, then I’ll give you a direct diagnosis and likely root cause.
I’m using the `kingdom` skill here because this is a `kd` ticket diagnosis. I’ve read `7397`; next I’ll quickly inspect the current TUI stream lifecycle to pinpoint exactly where visibility becomes inconsistent across rounds/providers.
I hit a path mismatch (`kd/...` doesn’t exist in this checkout). I’ll scan the actual repo layout and then re-run targeted searches in the right paths.
I found the relevant paths; now I’m reading the stream/panel code to isolate the concrete mechanism behind the first-round-only behavior and provider-specific visibility.
I’ve confirmed the extraction paths; next I’m checking message-panel lifecycle and IDs, because the “first message only” symptom usually means we’re updating an old widget instance instead of the current round’s panel.
I identified an additional timing factor: stream files are deleted immediately after finalization, so I’m checking the subprocess streaming writer to confirm whether fast responses can complete before the 100ms poll cycle ever sees thinking deltas.
I’ve narrowed it to a few concrete causes in code, and I’m grabbing exact line references so we can align on which ones are primary vs secondary.
It’s a multi-cause issue, not one bug.

1. Backend/event inconsistency
`kd` only renders thinking when a backend emits a recognized thinking event. Right now that is hard-coded to Cursor + Codex extractors in `src/kingdom/agent.py:627`, and Cursor specifically expects `{"type":"thinking","subtype":"delta"}` in `src/kingdom/agent.py:587`. If Cursor emits a different shape (or no thinking events), nothing shows.

2. Follow-up round UI lifecycle bug
Thinking panels are now persisted across messages, but they’re keyed only by member (`thinking-{name}`), reused globally, and updated in place: `src/kingdom/tui/app.py:629` and `src/kingdom/tui/app.py:631`.
In follow-up turns, that means we often update an old collapsed panel instead of showing a fresh live one near the current stream.

3. Collapsed panel doesn’t visibly refresh
`ThinkingPanel.update_thinking()` only redraws when expanded (`src/kingdom/tui/widgets.py:199`). So if the reused panel is collapsed, new thinking text can arrive with no visible change.

4. Poll timing race with cleanup
We poll every 100ms and process finalized messages before streams (`src/kingdom/tui/poll.py:87`-`src/kingdom/tui/poll.py:91`).
`run_query` unlinks `.stream-*.jsonl` immediately after finalization (`src/kingdom/tui/app.py:362`-`src/kingdom/tui/app.py:364`). Fast responses can finish before poller sees thinking deltas.

Net: inconsistency comes from both data availability (provider/event differences) and UI/poll lifecycle races.
