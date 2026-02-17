---
from: cursor
to: king
timestamp: 2026-02-17T01:17:35Z
---

I'm on it. Since I can't write the file directly, here is the proposed list of backlog tickets for `design.md`. This covers the CLI polish, TUI enhancements, and the interactive council permissions you mentioned.

### CLI Polish (`kd tk`)

*   **`tk log` command**: Implement a concise, one-line-per-ticket view (id, status, priority, title) similar to `git log` for quick scanning of the backlog.
*   **`tk show` formatting**: Improve the rendering of `tk show` to be more readable, perhaps using `rich` panels or tables for metadata.
*   **`tk list` sorting/filtering**: Ensure `tk list` has robust flags for filtering by status, assignee, or tag, and clear sorting defaults.

### TUI Polish (`kd chat`)

*   **Interactive Message Actions**: Add "Reply" and "Copy" buttons to `MessagePanel` widgets.
    *   *Reply*: Prefills the input area with a quote or reference to the message.
    *   *Copy*: Copies the message body to the clipboard.
*   **Input Area Enhancements**:
    *   **Tab Completion**: Implement tab-completion for `@` mentions (e.g., `@cla` -> `@claude`).
    *   **Syntax Highlighting**: Highlight `@mentions` and slash commands in the input area for better visibility.
*   **Dynamic Brand Colors**:
    *   Refactor `widgets.py` to remove hardcoded `DEFAULT_MEMBER_COLORS`.
    *   Load colors from `config.json` or derive them deterministically from the agent's name/backend so new agents feel "native" immediately.
*   **Thinking Visibility Toggle**: Add a hotkey (e.g., `t`) to toggle thinking visibility globally in the chat, overriding the auto-collapse behavior.
*   **Auto-Scroll Polish**: Improve the "smart scroll" behavior so it doesn't snap to bottom if the user is actively reading history when a new token arrives.

### Council Capabilities

*   **Interactive Ticket Management**:
    *   Give council members "write" permissions during chat.
    *   Allow agents to emit tool calls (e.g., `create_ticket`, `update_ticket`, `read_file`) that the `ChatApp` intercepts and executes (possibly with user confirmation).
    *   *Goal*: You should be able to say "@cursor create a ticket for X" and have it actually happen, rather than me just giving you the text for it.
*   **Context Awareness**: Ensure the `ChatApp` injects the current branch name and maybe a summary of `tk list` into the system prompt so we know what we're working on without you having to paste it.

### General

*   **Unified Error Handling**: Ensure all CLI and TUI errors use a consistent style (e.g., `rich` error panels) rather than raw tracebacks.
*   **Config Validation**: Improve `kd` startup to warn about invalid config keys or missing colors gracefully.

Does this cover the scope of "polish" you're looking for? I can refine the "Interactive Ticket Management" part—that sounds like the biggest lift.
