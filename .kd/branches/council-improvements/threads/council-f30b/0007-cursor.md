---
from: cursor
to: king
timestamp: 2026-02-15T00:06:24Z
---

Here is a comprehensive review of the `council-improvements` design document.

### Executive Summary

The design is directionally correct and addresses the core "liveness" issues. Moving to a TUI (`kd chat`) is the right architectural choice to decouple the viewing experience from the execution environment. However, the design underestimates the complexity of **concurrency** (in file-based threading), **stream parsing** (specifically for Codex/JSONL), and **process lifecycle management** (orphaned processes).

### Detailed Analysis

#### 1. Completeness
*   **Missing: Process Lifecycle Management.** The doc mentions "User typing interrupts auto-mode," but doesn't explain *how*. If `CouncilMember.query` spawns a subprocess (as seen in `src/kingdom/council/base.py`), simply stopping the TUI render loop doesn't kill the underlying LLM query. We need a mechanism to send `SIGTERM`/`SIGKILL` to the worker processes when the user interrupts or quits `kd chat`. Otherwise, you'll have "ghost" agents writing to thread files in the background.
*   **Missing: Context Management.** Group chat implies a potentially infinite loop. There is no mention of context window management. If a group chat goes for 10 rounds, does the context grow indefinitely? We need a sliding window or summarization strategy, or at least a hard token limit to prevent crashes.
*   **Missing: Initial State Loading.** When `kd chat` opens an existing thread, does it load *all* history? For long threads, this will be slow. The "pagination" requirement in Phase 1 helps `council show`, but the TUI needs a similar strategy (lazy loading) to start up quickly.

#### 2. Feasibility
*   **Hidden Complexity: JSONL Stream Parsing.** The doc notes Codex outputs JSONL. Parsing a *live stream* of JSONL is difficult because chunks often split right in the middle of a JSON object.
    *   *Risk:* The TUI will crash or flicker if it tries to `json.parse()` a partial line.
    *   *Recommendation:* The `CouncilMember` worker should ideally normalize the stream *before* writing to `.stream-*.md`, or the TUI needs a robust buffering parser that waits for newlines.
*   **Hidden Complexity: TUI Input vs. Async Loop.** Textual is async, but `input()` blocking can be tricky. Ensuring the user can type smoothly while 3 panels update at 60fps requires careful thread/worker management in Python.

#### 3. Dependencies
*   **Critical Path:** Phase 1 (Richer Status) is a strict dependency for Phase 2. The TUI cannot display "Running" vs "Timeout" if the underlying `CouncilMember` logic doesn't expose those states in a machine-readable way (e.g., via a `.status` file or specific log markers).
*   **Group Chat relies on Thread Safety:** Phase 3 (Group Chat) introduces multiple agents writing to the thread history automatically. If the thread system (file-based) isn't atomic, you will have race conditions where two agents overwrite each other's message files (e.g., both trying to write `005-message.md`).

#### 4. Risk
*   **Race Conditions:** As noted above, file-based threading is vulnerable to race conditions during the "Broadcast" phase if multiple agents finish simultaneously.
*   **"Zombie" Agents:** If the TUI crashes or is killed, background agents will continue running and writing to files, potentially corrupting the thread state for the next run.
*   **Context Desync:** If the TUI holds state in memory (Textual widgets) and the file system updates (background agents), keeping them in sync without full re-renders is error-prone.

#### 5. Config Design
The proposed `council.chat` config is a good start but missing key controls:
*   **Missing:** `interruption_behavior`: Should an interruption kill the current generation or just stop the *next* turn?
*   **Missing:** `context_limit`: To prevent cost runaways in auto-mode.
*   **Ambiguity:** `mode`: "broadcast" vs "sequential".
    *   *Critique:* "Broadcast" usually implies "send to all, they all reply, done". The doc implies "Broadcast *then* auto-turns". This hybrid mode is complex.
    *   *Suggestion:* Rename to `initial_turn`: `"broadcast" | "round_robin"` and `subsequent_turns`: `"round_robin" | "none"`.

#### 6. Streaming Architecture
*   **Location of Normalization:** The doc says "Reuse existing parse_codex_response()".
    *   *Critique:* If the TUI reads raw `.stream` files, it *must* implement the parsing logic. If the `CouncilMember` writes raw stdout (which includes JSONL for Codex) to the file, the TUI is burdened with backend-specific knowledge.
    *   *Recommendation:* Move normalization to the **Writer** side. The `CouncilMember` wrapper should parse the raw stdout from the subprocess and write *clean, human-readable text* to `.stream-{member}.md`. This makes the TUI dumb and generic (just tail the file).

#### 7. Thread System
*   **Concurrent Writes:** This is the biggest technical risk.
    *   *Current System:* Likely calculates the next sequence ID by listing files.
    *   *Problem:* Time-of-check to time-of-use (TOCTOU) bug. Agent A sees `004`, decides to write `005`. Agent B sees `004`, decides to write `005`. Last writer wins.
    *   *Fix:* Use a lock file (`thread.lock`) or use UUIDs for filenames and sort by timestamp/frontmatter sequence (if atomic).

#### 8. Textual as a Dependency
*   **Verdict:** **Yes.** It is the robust choice.
*   **Gotchas:**
    *   *Copy/Paste:* Terminals handle mouse selection differently. Textual overrides mouse events. Users might find it hard to copy code blocks out of the TUI unless you implement a "Copy" button or specific keybinding.
    *   *Layout:* Three vertical columns on small screens will be unreadable. You need a responsive layout (stack vertically on small screens, horizontally on large).

#### 9. The /mute /unmute Feature
*   **Contradiction:** "No slash commands" vs "Requirements: /mute".
*   **Resolution:** The "No slash commands" rule likely refers to *configuration* (changing models, temperatures). `/mute` is a *session control* command.
*   **Recommendation:** Allow `/mute` and `/unmute` as they are essential for managing noise in a group chat. Clarify the "No slash commands" rule to "No *configuration* slash commands".

#### 10. Auto-commit (1e3d)
*   **Design:** "After council responses complete".
*   **Problem:** In a continuous group chat, when is it "complete"?
*   **Recommendation:**
    *   **Manual Trigger:** `kd council commit` (or a button in TUI).
    *   **On Exit:** When the user quits `kd chat`, ask "Commit this session? [y/N]".
    *   **Auto:** Only auto-commit if the user explicitly configured `auto_commit: true`. Committing every single message is git-spam.

### Final Recommendation

Proceed with the design, but **add a specific technical task in Phase 2 to harden the Threading layer against concurrent writes.** Without that, the "Broadcast" and "Group Chat" features will result in data loss. Also, shift the stream normalization responsibility to the `CouncilMember` writer to keep the TUI simple.
