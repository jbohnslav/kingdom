---
from: claude
to: king
timestamp: 2026-02-16T20:42:18Z
---



Let me read the ticket and the relevant code to understand the issue.Let me also check the app.py to see how thinking panels are handled on finalization and follow-up rounds.OK, I can see the two remaining issues clearly now. Here's my analysis:

## Issue 1: Codex thinking not appearing on follow-up rounds

Look at `app.py:431` — `remove_member_panels`:

```python
def remove_member_panels(self, log: MessageLog, name: str) -> None:
    for prefix in ("wait", "stream", "interrupted"):
        for panel in list(log.query(f"#{prefix}-{name}")):
            panel.remove()
```

Good news: `"thinking"` was intentionally removed from this list (per the worklog fix). So that's not deleting the ThinkingPanel.

But the real problem is the **poller state**. When `run_query` finishes, it calls `stream_path.unlink()` at `app.py:363`, which deletes the stream file. Then on the follow-up round, the poller's `active_streams` for that member was cleared (in `poll_messages` at line 121-124: `active_streams.discard(sender)`, `thinking_texts.pop(sender, None)`).

So on the next round, a fresh stream file appears, and the poller correctly detects it as new (`StreamStarted`). The stream file starts writing... But here's the catch: the **ThinkingPanel from round 1 still exists in the DOM** with id `thinking-{name}`. When `handle_thinking_delta` runs for round 2, it finds the old panel via `query_one(f"#{panel_id}")` at line 631 and tries to update it. If the panel was collapsed from round 1, it updates the collapsed panel's text, but the collapsed state means the user doesn't see the new thinking. It *doesn't* re-expand it.

That's bug one: **auto-collapsed ThinkingPanel from a previous round is reused but never re-expanded** when new thinking arrives.

## Issue 2: Cursor thinking tokens still invisible

This is trickier. Look at `extract_cursor_stream_thinking` (`agent.py:587-603`) — it expects:
```json
{"type": "thinking", "subtype": "delta", "text": "..."}
```

But the question is: **does Cursor actually emit these events?** The ticket worklog says "Cursor does not emit `thinking` events on every prompt" (line 59). The `--stream-partial-output` flag is being passed (`agent.py:410`), but Cursor's thinking behavior depends on the model and mode. If Cursor is using a model with extended thinking (like Claude with thinking enabled), the thinking events might come in a different format — perhaps wrapped in `stream_event` like the text deltas, e.g.:

```json
{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"..."}}}
```

The current extractor only checks for top-level `{"type": "thinking", "subtype": "delta"}` — it doesn't unwrap `stream_event` wrappers, and it doesn't handle `thinking_delta` inside `content_block_delta`. So if Cursor wraps thinking in the same `stream_event` envelope as text, we're missing it entirely.

## Summary

Two distinct root causes:

1. **Codex follow-up rounds**: ThinkingPanel persists from round 1 in collapsed state. Round 2 reuses it via `query_one`, updates the text, but never calls `expand()`. Fix: in `handle_thinking_delta`, if the panel exists and is collapsed (and not `user_pinned`), re-expand it. Or: remove the old ThinkingPanel during `remove_member_panels` so a fresh one mounts.

2. **Cursor thinking invisible**: The extractor's expected event shape (`{"type":"thinking","subtype":"delta"}`) likely doesn't match what Cursor actually emits. Need to capture actual Cursor stream output (use `--debug-streams`) and see what thinking events look like. The fix might be handling `thinking_delta` inside `content_block_delta` wrapped in `stream_event`, similar to how `text_delta` is handled.
