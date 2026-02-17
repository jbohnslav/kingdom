---
from: codex
to: king
timestamp: 2026-02-17T11:05:10Z
---

Ticket `6e80` is the right call; this is a real UX bug, not cosmetic. I’d pull it next and patch the chat input so mouse click events cannot mutate composer text, then add a regression test for “clicking in chat does not insert characters.”
