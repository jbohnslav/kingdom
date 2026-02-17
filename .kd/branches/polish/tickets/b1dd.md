---
id: "b1dd"
status: closed
deps: []
links: []
created: 2026-02-17T03:04:15Z
type: task
priority: 2
---
# kd chat: slash command discoverability

Show available slash commands via autocomplete or hint bar in the UI, not just buried in /help.

## Work Log

### Implementation

- **SLASH_COMMANDS registry** in `widgets.py`: list of `(command, description)` tuples defining all available slash commands.
- **match_commands()** function: prefix-matching against command words, case-insensitive.
- **CommandHintBar widget**: docked above input, hidden by default. Shows matching commands when user types `/` prefix, hides otherwise.
- **Tab completion** in `InputArea.handle_tab_complete`: when input starts with `/` and has no spaces, cycles through matching slash command words.
- **on_text_area_changed handler** in `ChatApp`: drives hint bar visibility based on current input text.
- **Updated /help text**: mentions `/command` tab completion alongside `@mention`.
- **Tests**: `TestMatchCommands` (8 tests) and `TestCommandHintBar` (4 tests) in `test_tui_widgets.py`.
