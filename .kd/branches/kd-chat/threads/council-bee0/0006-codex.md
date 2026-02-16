---
from: codex
to: king
timestamp: 2026-02-16T19:32:50Z
---

I’d merge both: Claude’s implementation approach, with the tri-state behavior I proposed.

`Collapsible` is fine for static content, but for high-frequency streaming it can get awkward (layout churn, focus/scroll interactions, and less control over “don’t fight user” behavior). A custom `ThinkingPanel` is safer.

Recommended contract:

1. `auto` (default): show reasoning while it streams, auto-collapse on first answer token.
2. `show`: keep reasoning expanded.
3. `hide`: never render reasoning.

Two key rules to preserve UX quality:

1. Respect manual toggle (`user_pinned`): once user opens/closes, stop auto-collapsing/expanding.
2. Autoscroll only if viewport is already at bottom.

I’d also tweak Claude’s config suggestion: make it enum, not boolean.
Use something like `chat.thinking_visibility: auto|show|hide` (default `auto`).

So: yes, King, your hybrid instinct is the right direction. Claude’s widget caution + codex behavior model is the best combo.
