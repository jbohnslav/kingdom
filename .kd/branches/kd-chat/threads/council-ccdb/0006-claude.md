---
from: claude
to: king
timestamp: 2026-02-16T19:55:36Z
---

You're touching on something real. The three-panel setup you're describing isn't a messaging problem — it's a **multiplexing problem**. You have concurrent streams of work (ideation, execution, consultation) and you need to interleave them without losing context.

The danger isn't reimplementing IRC. The danger is reimplementing **tmux inside kd**. And I think we're already flirting with it.

Here's what I'd observe:

**What we actually have today:**
- Council threads: async multi-model Q&A, stored as markdown in `.kd/branches/<branch>/threads/`
- Peasant sessions: isolated execution in worktrees
- Your "idea capture" panel: just a Claude Code session where you run `kd tk create --backlog`

These aren't really "threads" in a messaging sense. They're **concurrent work contexts** that happen to produce text. The thread metaphor is misleading because it implies bidirectional conversation, but most of these are fire-and-forget or request-response.

**The rethink I'd propose:**

Instead of making threads richer, make them **thinner**. Right now each "panel" is a full agent session with its own context window, tools, and state. What if the mental model was closer to **unix pipes** than chat threads?

1. **Idea capture** shouldn't need an agent at all. `kd tk create --backlog "title"` already works from bare shell. If you want to dictate ideas, that's a one-liner, not a session.

2. **Council** is already correctly modeled as async request-response. The improvement isn't richer threading — it's better **notification**. You fire `kd council ask`, you get pinged when responses land. No persistent session needed.

3. **Execution** (peasants, hand work) is the only thing that genuinely needs a long-lived interactive session.

So instead of three panels with three agent sessions, you'd have: one active session for execution, a notification channel for async results (council, CI, peasants finishing), and shell aliases for quick fire-and-forget commands.

**The concrete simplification:**
- Kill the idea that council threads are "conversations." They're **queries with responses**. Model them that way.
- Add lightweight event notifications (`kd watch` or a status bar) so you don't need a dedicated panel to monitor async work.
- Keep the interactive session for the thing that actually needs interactivity: writing code.

The OpenClaw parallel here is instructive — they went the opposite direction, building a full gateway with WebSocket channels and session multiplexing, and now they have a massive ops surface to maintain. We should run *away* from that, not toward it.

The question I'd push back to you: of those three panels, which one do you actually **interact with** during a work session, versus which ones are you just watching for output?
