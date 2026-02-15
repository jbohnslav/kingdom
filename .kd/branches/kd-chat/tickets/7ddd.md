---
id: "7ddd"
status: open
deps: [bb51, fe84]
links: []
created: 2026-02-15T19:46:08Z
type: task
priority: 1
---
# ChatApp layout: header, message log, status bar, input area

## Context

Wire together the ChatApp Textual screen: header showing thread info, scrollable message log, status bar with keybinding hints, and input area. This is the main layout from the design wireframe.

## Acceptance Criteria

- [ ] `ChatApp` composes: Header, MessageLog (VerticalScroll), StatusBar, InputArea (TextArea)
- [ ] Header shows thread ID and member names
- [ ] StatusBar shows `Esc: interrupt · Enter: send · Shift+Enter: newline`
- [ ] InputArea uses Textual TextArea widget
- [ ] Message log is scrollable, takes remaining vertical space
- [ ] Auto-scroll: scroll to bottom on new content only if user is already at the bottom
- [ ] `kd chat --new` launches the app and displays the empty layout correctly
- [ ] App integrates polling via `set_interval(0.1, poll_updates)` calling `ThreadPoller`
