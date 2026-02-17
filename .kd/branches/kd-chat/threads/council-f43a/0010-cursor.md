---
from: cursor
to: king
timestamp: 2026-02-16T11:41:52Z
---

### Analysis & Recommendations

**1. Location: Create `src/kingdom/council/history.py`**
*   **Recommendation:** Do **not** put this in `thread.py`. `thread.py` is your data access layer (reading/writing files, parsing metadata). `format_thread_history` is *prompt engineering logic* specific to the council's operation.
*   **Why:** Putting it in `thread.py` couples your data model to specific LLM formatting needs. A dedicated module in `kingdom.council` keeps concerns separated and makes it easier to change prompt strategies later without touching file I/O code.

**2. Stripping Content: No**
*   **Recommendation:** Do **not** strip Markdown headers (like `## Response`) from the message body.
*   **Why:** `parse_message` already strips the YAML frontmatter. The Markdown body is the agent's content. Agents often use headers to structure their thoughts (e.g., `## Analysis`, `## Recommendation`). Stripping them indiscriminately risks destroying valuable semantic structure. If an agent is being too verbose, fix that via the system prompt (`council.preamble`), not by mutating the data.

**3. Directed Messages: Include All (with visual cues)**
*   **Recommendation:** Include **all** messages in the history, regardless of the `to` field.
*   **Refinement:** Update the format to indicate the recipient when it's not a broadcast.
    *   *Broadcast:* `king: What do you think?`
    *   *Directed:* `king (to claude): check the logs.`
*   **Why:** In a collaborative setting, agents need full context. If `king` asks `claude` a question and `claude` answers, `codex` needs to see the original question to understand `claude`'s answer or to correct it ("I see Claude said X, but..."). Filtering hides causality.

**4. Output Format: Solid, but needs the "To" indicator**
*   **Recommendation:** The general structure is correct. It creates a clear boundary between "what happened" and "what you need to do".
*   **Proposed Final Format:**
    ```text
    [Previous conversation]

    king: Let's fix the bug.

    claude (to king): I found the issue in api.py.

    codex: I can write the test for that.

    ---
    You are {target_member}. Continue the discussion.
    ```
*   **Note:** Ensure you preserve the exact order from `list_messages()`.

### Summary
*   **Module:** New `src/kingdom/council/history.py`.
*   **Content:** Raw body (no stripping).
*   **Visibility:** Total (all messages).
*   **Format:** Add `(to target)` indicator.
