---
from: codex
to: king
timestamp: 2026-02-16T19:28:20Z
---

I’d go with a tri-state behavior instead of just binary toggle:

1. `Auto` (default): show thinking live, then collapse when final answer starts.
2. `Show`: keep thinking expanded.
3. `Hide`: never render thinking content.

That matches what you described across UIs and gives power users control.

In Textual terms, this maps cleanly to a `Collapsible` + scrollable body (`RichLog` or `Markdown`), driven by reactive state:

- `mode: auto|show|hide`
- `is_reasoning: bool`
- `user_pinned_open: bool` (if they manually open/close, don’t fight them)
- `thinking_text: str`

Behavior I’d implement:

- On first reasoning chunk:
  - if `mode != hide`, mount/show the panel.
  - if `mode == auto` and not pinned, expand it.
- On first final-answer chunk:
  - if `mode == auto` and not pinned, collapse it.
- Keep a one-line collapsed header like `Thinking (2.1s, 1.3k tokens)` so it’s discoverable.

Important UX detail: autoscroll only if user is already at bottom. If they scroll up to inspect thinking, don’t yank focus.

So yes, a toggle is right, but I’d make it tri-state with `Auto` as the default.
