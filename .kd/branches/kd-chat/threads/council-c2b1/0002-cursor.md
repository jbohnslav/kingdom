---
from: cursor
to: king
timestamp: 2026-02-15T22:53:03Z
---

The ticket breakdown is excellent. It covers the full scope of the design document, from configuration changes to the complex TUI interactions. The tickets are granular, well-specified, and follow a logical implementation order.

I have two minor recommendations to improve parallelism and decouple logic from UI:

### 1. Decouple History Injection from Display
*   **Ticket:** `213e` (Thread history injection: `format_thread_history()`)
*   **Current Dependency:** `7656` (Thread history display on open)
*   **Recommendation:** **Remove the dependency on `7656`.**
    *   `format_thread_history` is a logic function (likely in `kingdom.council` or `kingdom.thread`) that reads files and produces a string. It does not depend on the TUI's ability to display messages.
    *   This allows `213e` to be implemented in parallel with the TUI work.

### 2. Decouple Streaming Display from User Input
*   **Ticket:** `4a91` (Streaming display: connect polling to widget lifecycle)
*   **Current Dependency:** `16e1` (User input, query dispatch...)
*   **Recommendation:** **Remove the dependency on `16e1`.**
    *   You can verify streaming display by running `kd council ask --async ...` in a separate terminal and watching the TUI pick it up (as noted in your acceptance criteria: *"In-flight external stream files shown"*).
    *   This allows the streaming visualization logic to be built and tested before the input/dispatch mechanism is fully wired up.

**Summary:**
The plan is solid. With those two dependency tweaks, you'll have a slightly more flexible execution path. No other missing items or incorrect scopes were found.
