---
from: cursor
to: king
timestamp: 2026-02-16T19:28:56Z
---

I've read ticket 7397. This is a great UX improvement — seeing the "thought process" makes the wait feel much shorter and gives confidence that the agent isn't stuck.

Regarding the UI implementation in Textual:

1.  **Widget Choice**: Textual has a built-in `Collapsible` widget which is perfect for this. We can put the thinking tokens inside a `Collapsible` and the final response below it.
2.  **Behavior**:
    *   **Streaming Phase**: We can keep the `Collapsible` expanded (and maybe auto-scroll to bottom) while "thinking" events are coming in.
    *   **Answer Phase**: Once the first real content token arrives, we can automatically collapse the `Collapsible` so the user sees the answer, but can expand it back if they want to inspect the reasoning.
    *   **Styling**: We can style the content inside the `Collapsible` to be greyed out (`color: $text-muted`) to distinguish it from the final answer.

To make this work, we'll need to:
1.  Update `extract_stream_text` in `agent.py` to parse `thinking` events (currently it only looks for `content_block_delta` and `assistant` text).
2.  Update `StreamDelta` in `poll.py` to carry both `thinking_text` and `content_text`.
3.  Refactor `StreamingPanel` in `widgets.py` from a simple `Static` to a container (like `Vertical`) that holds a `Collapsible` (for thoughts) and a `Static` (for the answer).

This approach gives us the best of both worlds: visibility when it's happening, but a clean reading experience for the final result.
