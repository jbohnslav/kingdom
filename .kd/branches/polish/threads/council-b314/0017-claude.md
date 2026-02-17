---
from: claude
to: king
timestamp: 2026-02-17T11:04:41Z
---

The King is frustrated that the chat TUI is inserting extra characters (looks like commas or some other character) every time they click in it. This is a real bug worth tracking.

Let me create the backlog ticket.Created backlog ticket **6e80**: *Chat TUI: clicking in the UI inserts extra characters (commas)*

This is likely a mouse event handling issue in the Textual TUI — click events are being interpreted as text input. I can look into it now if you want, or it can wait in the backlog.
