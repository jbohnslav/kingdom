---
from: cursor
to: king
timestamp: 2026-02-15T18:55:48Z
---

The design document in `.kd/branches/kd-chat/design.md` lays out a solid foundation for the `kd chat` feature, leveraging the existing thread and streaming infrastructure. Using `Textual` for the TUI and existing thread files for persistence are excellent choices that align with the project's architecture.

However, to fully realize the "group chat with my best engineers" vision, there are a few missing pieces and key decisions to address.

### Analysis & Recommendations

**1. "Best Engineers" Persona & Configuration**
*   **Current State:** `CouncilMember` has a hardcoded `COUNCIL_PREAMBLE` that explicitly instructs agents: *"Do NOT create, edit, delete, or write source code... Respond with analysis and recommendations — do not implement anything."*
*   **Problem:** This conflicts with the goal of having "best engineers" who might need to show code snippets or be more hands-on in their advice.
*   **Recommendation:** Move the preamble to `config.json` or make it overridable per-agent. You likely want a `council.personas` section in the config where you can define "Engineer", "Architect", "QA", etc., and assign them to specific backends.

**2. Thread History Injection (Crucial for Group Chat)**
*   **Current State:** The design notes this as "New logic needed". Currently, `CouncilMember.build_command` simply appends the user prompt to the system prompts.
*   **Problem:** For a true group chat experience, agents need to see what *other* agents have said.
*   **Recommendation:** Implement a `format_thread_history(thread_id)` function in `Council`.
    *   **Decision:** Should this be passed as a raw string in the `prompt`, or does `CouncilMember` need to support a list of messages? Passing it as part of the `prompt` string is the simplest path for CLI-based agents, but you must decide on a clear format (e.g., `[Claude]: ... \n [Codex]: ...`) that the models will understand as a dialogue.

**3. Context Window Management**
*   **Missing:** The design does not address what happens when the thread history exceeds the context window.
*   **Recommendation:** Decide on a simple truncation strategy up front.
    *   **Option A (Simple):** Keep only the last N messages or roughly N tokens.
    *   **Option B (Smarter):** Keep the initial system prompt + the user's first message + the last N messages.
    *   *Decision:* Start with Option A (e.g., last 20 messages) to prevent "context overflow" errors during long brainstorming sessions.

**4. Auto-Round Interrupt Handling**
*   **Current State:** "User typing interrupts auto-mode: stops scheduling new turns".
*   **Risk:** This can be tricky to implement cleanly in an async loop.
*   **Recommendation:** Implement a simple "interrupt flag" in the TUI state. Before scheduling the next auto-turn, check `if user_is_typing or user_sent_message: stop_auto_rounds()`. Don't try to kill the *currently running* generation (as the design suggests), just prevent the *next* one.

**5. Rendering & Artifacts**
*   **Missing:** How to display code blocks or artifacts produced by the "engineers".
*   **Recommendation:** Ensure the Textual `Markdown` widget is configured to handle syntax highlighting. If agents produce "artifacts" (like separate files), the TUI should probably just render them as code blocks within the chat for now, rather than trying to manage a separate "file view" pane in Phase 1.

### Summary of Key Decisions to Make Up Front

1.  **Preamble/Persona:** Will you allow these "engineers" to write code? If so, the hardcoded `COUNCIL_PREAMBLE` **must** be changed or made configurable immediately.
2.  **History Format:** Define the exact text format for injecting thread history (e.g., `User: ...\nAgent Name: ...`) so all models parse the conversation flow correctly.
3.  **Context Limit:** Pick a hard limit for history injection (e.g., "Last 10 messages") to avoid immediate cost/token issues.

The plan is otherwise sound. The decision to use `Textual` and existing file-based persistence is the right approach for a robust, crash-safe tool.
