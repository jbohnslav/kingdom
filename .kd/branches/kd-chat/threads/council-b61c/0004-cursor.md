---
from: cursor
to: king
timestamp: 2026-02-16T20:46:21Z
---

The inconsistent thinking visibility stems from two race conditions in `ThreadPoller` and a lifecycle issue in `ThinkingPanel` persistence.

**1. Polling Order Race (The "Invisible" Last Chunk)**
Currently, `poll()` runs `poll_messages()` *before* `poll_streams()`.
- When an agent finishes, it writes the message file and deletes the stream file almost simultaneously.
- If `poll_messages()` runs first, it detects the new message and **immediately clears the stream state** (thinking text, offsets).
- This causes us to discard the final chunk of thinking data (which often arrives in the very last stream flush) before `poll_streams()` can read it.
- **Fix:** `poll_streams()` must run *first* to capture the latest data. Cleanup should only happen in `poll_streams()` when it confirms the file is actually gone.

**2. Panel ID Collision (The "Hidden" Follow-up)**
The `ThinkingPanel` uses a static ID: `thinking-{member}`.
- In follow-up rounds, the `ThinkingPanel` from the previous round still exists (persisted & collapsed).
- When new thinking arrives, `handle_thinking_delta` finds the *old* panel and updates it.
- Since that panel is collapsed, the new thinking updates the character count in the collapsed header but remains hidden. The user expects a new, expanded panel for the new thought process.
- **Fix:** When a message is finalized, we must "archive" the thinking panel by renaming its ID (e.g., to `thinking-{member}-{sequence}`). This forces the next round to create a fresh, expanded `ThinkingPanel`.

**3. "Ghost" Streams**
Because `poll_messages` clears state while the stream file might still exist for a few milliseconds, the next `poll_streams` cycle treats the lingering file as a *new* stream (offset 0), triggering a "ghost" stream start event.
- **Fix:** `poll_messages` should not clear stream state. We should let `poll_streams` manage the lifecycle and only clear state when the file is physically removed.

I have applied these fixes to `poll.py` and `app.py`.
