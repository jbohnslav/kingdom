---
from: cursor
to: king
timestamp: 2026-02-16T12:09:26Z
---

### Analysis of the Provided Prompt Structure

This snippet effectively demonstrates the proposed `format_thread_history` output (Ticket 213e), but it highlights two specific implementation issues we need to handle in `kingdom.council` or `kingdom.thread`.

**1. The "Double Name" Bug**
*   **Observation:** The history shows `codex: codex: Hello...` and `codex: codex: poop`.
*   **Cause:** This happens when an agent (Codex) is prompted with `codex:` at the end of the input, and it "completes" the pattern by repeating its name before the message.
*   **Recommendation:** In `CouncilMember.parse_response` (or `add_message`), we must **strip the leading "Name:"** if the model generates it. The message body stored on disk should *only* contain the content, not the speaker label.

**2. Meta-Commentary in History**
*   **Observation:** The entry for `cursor` contains my previous Advisor analysis ("This is a correctly formatted prompt...").
*   **Implication:** If an agent (or the system) outputs meta-text, errors, or refusals, these become permanent parts of the thread history.
*   **Recommendation:** Ensure that `format_thread_history` creates a clean context. If an agent previously output an error (e.g., `*Error: Timeout*`), we might want to exclude that turn or format it differently (e.g., `[cursor timed out]`) so the next agent doesn't get confused by the error text.

**3. Directed Message Format**
*   **Observation:** `king (to cursor):` works well to establish directionality.
*   **Recommendation:** Proceed with this format for `Ticket 213e`.

**Summary:** The format works, but you must implement a **"name prefix stripper"** in the response parsing logic to prevent `codex: codex:` artifacts.
