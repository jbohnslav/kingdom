---
from: cursor
to: king
timestamp: 2026-02-16T19:36:24Z
---

I'm on board. Since we're stuck in read-only mode, here are the exact updates for you to apply, King.

First, for **ticket b057**, let's capture the chat-specific requirement Codex identified.

```markdown
# Add this to the Acceptance Criteria in .kd/backlog/tickets/b057.md:

- [ ] Writable mode works end-to-end in `kd chat` TUI, including permission mediation (approve/deny prompts)
```

Second, for **ticket 7397**, here is the full design update based on our discussion. You can replace the current "Acceptance Criteria" section and add the "Design" section.

```markdown
# Update for .kd/branches/kd-chat/tickets/7397.md

## Design

- **Config**: `chat.thinking_visibility: auto | show | hide` (default: `auto`)
- **`auto`**: stream thinking live, auto-collapse on first answer token into a one-line summary like `"▶ thinking · 1,247 chars · 4.2s"`. Click/Enter to re-expand.
- **`show`**: keep thinking expanded always.
- **`hide`**: drop thinking events (current behavior).
- **Widget**: Custom `ThinkingPanel`, not Textual `Collapsible`. Follows existing panel patterns. ~40-50 lines.
- **Key rules**: `user_pinned` flag — once user manually toggles, stop auto-collapsing. Autoscroll only if viewport is at bottom.
- **Stream layer**: Extend `extract_*_stream_text` to parse `thinking_delta` events; `ThreadPoller` emits `ThinkingDelta`.

## Acceptance Criteria

- [ ] Implement `ThinkingPanel` widget with expanded/collapsed states
- [ ] Add `chat.thinking_visibility` config with `auto` (default), `show`, `hide` options
- [ ] Implement `auto` behavior: expand on thinking start, collapse on answer start
- [ ] Implement `user_pinned` logic: manual toggle overrides auto-collapse
- [ ] Update stream parsing to handle `thinking` events and emit `ThinkingDelta`
- [ ] Ensure autoscroll respects user scroll position (don't yank if scrolled up)

## Worklog

- 2026-02-16: Ticket created from live debug stream analysis (`council-72f2`) showing Cursor emits `thinking` events that are currently not rendered in TUI.
- 2026-02-16: Design finalized in council-8351. Tri-state config, custom ThinkingPanel, user_pinned respect. Combines Claude's implementation + Codex's behavior model.
```

Once you've applied these, we can move forward with the implementation plan for 7397.
