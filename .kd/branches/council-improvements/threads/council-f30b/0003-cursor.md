---
from: cursor
to: king
timestamp: 2026-02-14T23:33:35Z
---

The current "unnatural" feeling stems from a specific disconnect in the implementation: while `Council.query_to_thread` *does* write real-time output to `.stream-{member}.md` files, the `kd council watch` command (and `watch_thread` function) **ignores these streams entirely**. It polls only for *completed* messages added to the thread history. This explains the "four-minute spinner" followed by a sudden dump of text.

Here is a comprehensive analysis and recommendation for a `kd chat` TUI to solve this.

### 1. The Diagnosis: Why it feels "dead"
Currently, the user is disconnected from the agent's "thinking" process.
*   **The Backend:** `CouncilMember.query` correctly tees output to a stream file.
*   **The Frontend:** `watch_thread` waits for the process to exit and the message to be finalized before rendering anything.
*   **The Result:** You miss the most important feedback loop—seeing *what* the agent is considering, which allows for early cancellation if it's going off-track.

### 2. The Solution: `kd chat` TUI
I recommend building a dedicated TUI application using **Textual** (a Python framework for TUIs). It is robust, supports async natively, and can handle the complex layout we need.

#### A. Interface Design: "Unified but Distinct"
Instead of 3 separate panes (which you noted is a pain), use a **single unified timeline** (like iMessage/Slack) but with "live" bubbles.

*   **The Stream Bubble:** When you send a message, three empty bubbles appear immediately.
*   **Live Streaming:** As agents write to `.stream-{member}.md`, these bubbles fill up character-by-character in real-time.
*   **Color Coding:**
    *   **Claude:** Purple border/tint.
    *   **Codex:** Green border/tint.
    *   **Agent:** Blue border/tint.
*   **Typing Indicators:** Not just "..." but the actual token stream.

#### B. Architecture & Workflow
Since this cannot run inside Claude Code's TUI effectively, the workflow would be:

1.  **Main Pane (Claude Code):** You work on code, run tests.
2.  **Side Pane (Tmux):** You run `kd chat`. This is your "War Room".
3.  **Interaction:**
    *   You type in `kd chat`.
    *   The TUI spawns the council workers (backgrounded).
    *   The TUI tails the file streams and updates the UI.
    *   **Crucially:** The chat history is saved to the standard Kingdom thread format.
4.  **Loop Back:** When the council finishes, a summary or the final decision can be pulled back into the Claude Code context via `kd council summary` or simply by the fact that the thread is updated.

### 3. "Group Chat" Dynamics (The Reach Goal)
To achieve the "Slack thread with engineers" feel, we need to move beyond the current "Parallel Query" model.

**Current Model:** User -> [A, B, C] (Parallel, Independent).
**Proposed Model:** Event-Driven Conversation.

*   **Phase 1: Broadcast.** You send a message. It goes to A, B, C.
*   **Phase 2: The "Floor".**
    *   We implement a `kd council debate` mode.
    *   After the initial round, the system constructs a prompt: *"Here is what User, B, and C said. Do you have a correction or addition? If not, reply SKIP."*
    *   **Orchestrator:** A simple loop that checks the stream. If Agent A references Agent B, or if a "Conflict Detected" heuristic triggers, it prompts the others.

**SillyTavern Inspiration:**
We can adopt SillyTavern's **"Group Chat" settings**:
*   **Message Limit:** "Allow max 3 auto-replies between agents before pausing for User."
*   **Randomness:** "Randomly select next speaker" vs "Round Robin".
*   **Mention Awareness:** If Agent A says "@Codex, check this", the system forces Codex to run next.

### 4. Implementation Steps

#### Step 1: Fix the immediate pain (The "Quick Win")
Modify `src/kingdom/cli.py:watch_thread` to **tail the `.stream-*.md` files**.
*   Instead of just polling `list_messages`, also glob for `.stream-*.md` in the thread directory.
*   Read the last few lines of these files and print them to the console (even if just as ephemeral text above the spinner).
*   **Benefit:** Immediate visibility into the "thinking" process without a full rewrite.

#### Step 2: Build the `kd chat` TUI
Create `src/kingdom/tui.py` using Textual.
*   **Widgets:** `Log` widget for the chat, `Input` for the user.
*   **Watcher:** `FileSystemWatcher` on the thread directory.
*   **Action:** When a `.stream` file changes, update the corresponding message bubble in the TUI.

#### Step 3: The "Debate" Logic
Implement a `Council.debate()` method.
*   It runs the initial query.
*   Then enters a loop:
    *   Check if any agent output ends with a question or challenge.
    *   If so, trigger the targeted agent (or all) with the new context.
    *   Stop after N turns or when all agents say "SKIP".

### Recommendation Summary

1.  **Don't use tmux panes for agents.** It fractures the context. Use a **single TUI** that aggregates streams.
2.  **Revive `kd chat`** but build it with **Textual**, not a hacky loop.
3.  **Run it side-by-side.** Keep Claude Code for *doing*, use `kd chat` for *discussing*.
4.  **Immediate Action:** I can patch `watch_thread` right now to show streaming output, which might solve 80% of the frustration before you even build the TUI.

**Would you like me to prototype the `watch_thread` fix (streaming visibility) first, or start scaffolding the `kd chat` TUI?**
