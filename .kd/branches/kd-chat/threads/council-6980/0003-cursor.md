---
from: cursor
to: king
timestamp: 2026-02-16T20:26:11Z
---

The issue is that `handle_new_message` (which runs when the final message arrives) was deleting *all* temporary panels for that member—including the `ThinkingPanel`. This caused the thinking widget (and its tokens) to vanish just as the response finalized, leaving no clickable history.

I've updated `src/kingdom/tui/app.py` to preserve the `ThinkingPanel` when a new message arrives. Now:
1.  The `ThinkingPanel` is **not removed** upon completion.
2.  It is explicitly **collapsed** (if `thinking_visibility` is `auto`), turning it into the clickable summary widget you expect (`▶ codex thinking · N chars · Xs`).
3.  The final message is inserted *after* the thinking panel, preserving the logical order: `[Thinking] -> [Answer]`.

This ensures the thinking process remains accessible and clickable even after the agent has finished replying.

I also added a test case in `tests/test_tui_thinking_persistence.py` to verify this lifecycle behavior.

You should now see the Codex thinking tokens persist as a clickable widget after the response is complete.

(No other changes were needed for Codex specifically, as the token extraction was already working as you noted.)
