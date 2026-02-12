---
from: cursor
to: king
timestamp: 2026-02-09T16:39:38Z
---

To allow you to ask the council without Claude Code (the Hand) "taking over" or synthesizing the response, I have updated the design with a **split-brain workflow** using two commands.

Here is the update to `.kd/branches/refactor-multi-agent/design.md`:

1.  **`kd council ask --async`**: Added a flag to fire off the request and return immediately (with the thread ID) instead of waiting for the response. This means the Hand (Claude Code) only sees "Thread started: council-123" and doesn't get the chance to digest the actual opinions.
2.  **`kd council watch <thread-id>`**: Added a command to live-stream the conversation. You can run this in a second terminal (tmux pane) to watch the debate unfold raw, preserving the "direct" connection to the advisors.

**The Workflow:**
1.  **In Claude Code (The Hand):**
    ```bash
    kd council ask --async "Should we use Redis?"
    # Output: Council debate started in thread 'council-redis'
    ```
2.  **In a separate terminal (The King):**
    ```bash
    kd council watch council-redis
    # Output: Live stream of the advisors' debate...
    ```

This satisfies your request to "run two separate commands... show it second" and ensures you see the raw responses without interference.
