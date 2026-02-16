---
id: "ecf7"
status: open
deps: []
links: []
created: 2026-02-16T12:13:12Z
type: bug
priority: 2
---
# kd chat: mouse reporting makes copy/paste hard in Textual

In `kd chat` (Textual TUI), terminal mouse reporting appears to interfere with normal text selection/copy-paste UX.

Repro:
1. Run `kd chat ...`
2. Try to select and copy text with mouse in terminal
3. Selection/copy is unreliable or blocked due to mouse reporting capture

Expected:
- Users can reliably copy text from chat output (and paste into input) in common terminals.
- If full mouse mode is required for interaction, provide a clear toggle/command or alternative copy-friendly mode.

Possible directions:
- Add config/flag to disable mouse capture for copy-focused sessions.
- Add slash command or keybinding to toggle mouse support at runtime.
- Document terminal-specific behavior/workarounds if unavoidable.
