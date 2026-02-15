---
from: cursor
to: king
timestamp: 2026-02-15T02:41:40Z
---

Based on the review of the design document and the current tickets, here is my analysis and recommendations.

### 1. Alignment Check
The tickets largely align with the design, but the **Phase 2 (TUI)** and **Phase 3 (Group Chat)** work is compressed into a single, vague ticket (`3e60`) which hides significant complexity. Additionally, the critical technical risk of **concurrent writes** identified in the design review has no corresponding ticket.

### 2. Missing Items
*   **Thread Safety Hardening:** The design relies on multiple agents writing to the thread history in "Group Chat" mode. The current file-based thread system (likely using `list_messages()` to find the next sequence number) is vulnerable to race conditions. **We need a ticket to implement atomic writes or locking.**
*   **Group Chat Logic vs. UI:** Ticket `3e60` conflates "Building the TUI" with "Implementing the Group Chat Auto-Pilot". These are separate concerns. The TUI is a view layer; the Group Chat logic is an orchestration layer (likely running in the background or within the TUI process).

### 3. Recommendations

#### A. Split Ticket `3e60` (Council Chat Room)
This ticket is too broad. Split it into:
1.  **`kd chat` TUI (View Layer):** Build the Textual app, file polling, input handling, and rendering of `.stream-{member}.jsonl` files.
2.  **Group Chat Orchestration (Logic Layer):** Implement the `auto_rounds` logic, round-robin scheduling, and the "broadcast then sequential" state machine.

#### B. Create New Ticket: "Harden thread system for concurrency"
*   **Why:** Without this, Phase 3 (Group Chat) will result in overwritten/lost messages when agents respond quickly.
*   **Scope:** Implement a locking mechanism (e.g., `thread.lock` file) or random-suffix filenames with timestamp sorting to ensure multiple processes can write to the same thread directory safely.

#### C. Update Ticket `e756` (Stream JSON)
*   **Refinement:** Ensure the "New `extract_stream_text` function" AC explicitly mentions that it should be used by both `watch_thread` (CLI) and the new TUI. This ensures code reuse.

### 4. Proposed Plan Updates

I recommend creating the following tickets to fill the gaps:

```markdown
# Harden thread system for concurrent writes
- Implement file locking or atomic write strategy for thread messages
- Ensure `add_message` is safe to call from multiple parallel processes
- Verify sequence numbers don't collide

# Implement Group Chat Auto-Pilot Logic
- Implement `council.chat` config reading
- Implement the "Broadcast -> Auto-Round" state machine
- Implement the "Round Robin" scheduling logic
- Handle "Stop Conditions" (max rounds, empty responses)
```

And update `3e60` to focus purely on the **Textual TUI implementation**.

### 5. Conclusion
The plan is solid, but the "Group Chat" feature is currently under-specified in the tickets. Breaking it down and addressing the concurrency risk upfront will save significant debugging time later. The "Phase 0" work in `e756` is the correct first step.
