---
from: claude
to: king
timestamp: 2026-02-15T18:58:56Z
---



I'll start by reading the design doc and understanding the current codebase to give you a thorough review.Let me read the relevant CLI sections — the council commands and the watch implementation.Now let me read the watch_thread implementation and the council_ask CLI function to understand the current UX.Now I have a thorough understanding of both the design doc and the existing codebase. Here's my review.

---

## Design Doc Review: `kd chat`

### Overall Assessment

This is a **solid design doc**. The phased approach is right, the decision to build on top of thread files as source of truth is the correct call, and the non-goals are well-chosen. The existing infrastructure (stream files, NDJSON extraction, thread CRUD, watch polling) gives you a strong foundation. That said, there are gaps and some decisions I'd push you to nail down before writing code.

### What's Good

1. **File-based source of truth** — Keeping thread files as the canonical state means crash safety for free, `kd council show` compatibility, and no new state to manage. Perfect.

2. **Textual over Rich Live** — Correct call. You'd reinvent scroll, input, and layout otherwise. Optional dependency is the right packaging move.

3. **Phased delivery** — Phase 1 (TUI view+input) is independently useful before group chat lands. Good decomposition.

4. **"Interrupt = queue, not kill"** — This is the non-obvious right answer. Killing mid-generation wastes tokens and corrupts stream files.

5. **Thread history injection for group chat** — Explicitly calling out that session resume is per-agent and won't give cross-agent awareness shows you've thought about the hard part.

### What's Missing

**1. The TUI architecture itself is unspecified.**

The doc says "Textual app" but doesn't describe the widget tree. For a breakdown to be actionable, you need at least:
- What's the layout? A scrollable message log on top, input bar at bottom? Sidebar with member status?
- How does markdown rendering work inside Textual? Textual has `Markdown` and `RichLog` widgets, but Rich Markdown panels in a scrollable Textual container need thought. Are you rendering each message as a `Static` with Rich markup, or using Textual's `Markdown` widget per message?
- How does the streaming preview appear? A separate area per member? Inline in the message log with a "typing..." indicator? This is the core UX question.

**Recommendation:** Add a "Layout" section with an ASCII wireframe. Something like:

```
┌─────────────────────────────────────┐
│ [king] What should we do about X?   │
│                                     │
│ [claude] I think we should...       │
│ (streaming: 1,234 chars)            │
│                                     │
│ [codex] ▍ typing...                 │
│                                     │
├─────────────────────────────────────┤
│ > your message here                 │
└─────────────────────────────────────┘
```

**2. No discussion of how multi-line input works.**

In a chat TUI, Enter usually sends. But engineers write code blocks and multi-line thoughts. What's the send key — Enter or Ctrl+Enter? Does Shift+Enter insert a newline? This is a UX decision that matters for the "group chat with engineers" feel.

**3. Thread resumption semantics are underspecified.**

`kd chat` resumes current thread, `kd chat --new` creates fresh. But:
- What if there are 5 old threads? Is there a `kd chat <thread-id>` to pick one?
- When resuming, do you show the full history or just the last N turns?
- What happens if you `kd chat` while a background `kd council ask --async` is still running on the same thread? The TUI would need to pick up the in-flight stream files.

**4. No error display strategy.**

When a member errors or times out, how does the TUI show it? A red panel? An inline error message? Does it auto-retry or show a prompt like "claude errored — /retry?"

**5. The relationship between `kd chat` and `kd council ask` is unclear.**

Can they coexist on the same thread? If I `kd council ask` something, then open `kd chat`, I should see that history. But if I have the TUI open and someone runs `kd council ask` in another terminal — does the TUI pick that up? The file-based source of truth makes this *possible*, but the doc should state whether this is supported or explicitly a non-goal.

**6. Group chat prompt construction isn't specified.**

The doc says "auto-turns build full thread context into the prompt" but doesn't define the format. This matters because:
- How do you format a multi-party conversation for an LLM that expects a single user prompt? Something like:

```
[Previous conversation]
king: What should we do about X?
claude: I think we should...
codex: I disagree because...

[Your turn]
You are codex. Continue the discussion. Respond to the points raised above.
```

- How much history fits in context? With 3 members and 3 rounds, that's 9+ messages. Some could be huge. Do you truncate?
- Do you strip the safety preamble from the history representation? (You should — it's instruction, not conversation.)

**7. Missing: what happens to session resume in group chat.**

The doc says thread history injection, not session resume. But the current `CouncilMember.build_command()` always passes `self.session_id` which triggers `--resume`. In group chat mode, do you:
- Still use session resume (for per-agent context) AND inject thread history (for cross-agent awareness)?
- Drop session resume entirely and rely only on thread history?

This is a key architectural decision. Using both means duplicated context (the agent's own prior messages appear twice). Using only thread history means losing tool use context from prior turns. I'd recommend **thread history only** for group chat, which means a new code path that builds commands without `--resume`.

### What's Incorrect or Risky

**1. "Poll at 250ms" may not be enough for smooth token streaming.**

For the CLI `watch_thread()` this is fine — you're showing a preview snippet. But in a TUI where you're rendering streaming text character-by-character into a scrollable widget, 250ms polls will feel chunky. Consider 100ms, or better yet, use `asyncio.sleep(0.1)` in the Textual async loop and let Textual batch rendering updates.

**2. `asyncio.to_thread()` for blocking subprocess queries is correct but incomplete.**

The `CouncilMember.query()` method blocks on subprocess + threading. Wrapping it in `asyncio.to_thread()` works, but you need to think about cancellation. If the user `/quit`s mid-generation, you need to kill the subprocess. The current `query_once()` doesn't expose the `Popen` handle for external cancellation. You'll likely need a new async-aware query method or a cancellation token pattern.

**3. Config validation will reject `council.chat` keys.**

`VALID_COUNCIL_KEYS = {"members", "timeout"}` in config.py. Adding `auto_rounds` and `mode` requires updating validation. This is trivial but worth noting in the design so it doesn't get missed.

### Key Decisions to Make Up Front

1. **Streaming display: per-message inline vs. dedicated streaming area?** Inline (message appears in the log and grows as tokens arrive) feels more like a real chat. Dedicated area (separate panel that clears when message finalizes) is simpler to implement.

2. **Enter vs. Ctrl+Enter to send?** Ctrl+Enter is more engineer-friendly (preserves Enter for newlines). But it's less chat-like.

3. **Session resume in group chat: keep, drop, or make configurable?** I recommend drop (thread history only) for simplicity.

4. **Should the TUI module live as a new top-level module (e.g., `kingdom/tui.py` or `kingdom/tui/`) or be folded into cli.py?** Given cli.py is already 3300 lines, a separate module is strongly recommended. Probably `kingdom/tui/app.py` with the Textual `App` subclass.

5. **How does `/mute` interact with group chat auto-rounds?** If I mute codex, does it skip codex in the round-robin, or does it just hide codex's output? Skipping is more useful (saves tokens), but then "session-scoped mute" becomes a behavior change, not just a display filter.

6. **Max history size for thread injection.** With verbose LLM responses, 3 rounds of 3 members could be 50k+ tokens in the prompt. You need a truncation or summarization strategy, even if it's just "last N messages" or "last N characters per message."

### Summary

The design is 80% there. The core architectural decisions (Textual, file-based state, polling, round-robin with hard cap) are all correct. What's missing is the TUI-specific details: layout, widget architecture, streaming display strategy, input handling, and the exact prompt format for group chat history injection. I'd address these before breaking down into tickets — they're the decisions that will shape every ticket's implementation.
