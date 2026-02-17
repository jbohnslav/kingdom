---
from: codex
to: king
timestamp: 2026-02-17T01:31:19Z
---

I’m going to quickly check the `kingdom` skill instructions so my recommendation matches your branch workflow and ticket hygiene rules, then I’ll give a concrete codex position on Claude’s proposed split.
I agree with Claude’s direction, with a tighter cut so this stays “polish” and doesn’t become a feature branch.

What I’d change in his draft:
- Move `1e3d` (auto-commit council threads) to backlog. It changes safety semantics.
- Move `c247` (thread auto-pickup) to backlog unless we keep it to copy-only UX text tweaks.
- Don’t make `c937` part of this PR scope; dropping members is an ops/config decision you can do immediately, not a polish ticket set dependency.

My recommendation on the 2 open questions:
- `kd tk log`: make it an event log (state transitions + worklog entries + assignment/deps), not a separate manual journal.
- Reply behavior: insert a compact quote (first lines) plus message reference, not full-body quote by default.

If you want a strict “new tickets to create now” list (excluding existing IDs), I’d create these first:
1. `kd chat`: Reply action on messages (quote + `@author`).
2. `kd chat`: Copy Markdown action (alongside plain copy).
3. `kd chat`: Copy/reply success toast/status.
4. `kd chat`: Keyboard shortcuts for message actions (`r`/`c`).
5. `kd chat`: Keep action buttons keyboard-focusable (not hover-only).
6. `kd chat`: Slash command discoverability in composer.
7. `kd chat`: Thinking duration format `mm:ss` when >60s.
8. `kd chat`: Error panel with concrete retry hint.
9. `kd chat`: Smart autoscroll that won’t snap while reading history.
10. `kd chat`: Expand fallback member palette to avoid collisions.
11. `kd tk list`: Rich table rendering for scanability.
12. `kd tk show`: Structured Rich panel layout.
13. `kd tk move`: Human-readable success destination text.
14. `kd cli`: Standardized Rich error output across commands.
15. `kd cli`: Standardized empty-state + next-step hints.
16. `kd cli`: Cleaner Ctrl+C interruption messaging.
17. `kd council status`: Symbol legend output.
18. `kd council show`: `--last N` for long threads.

If you want, I can now give the exact `kd tk create --backlog "..."` command list in priority order.
