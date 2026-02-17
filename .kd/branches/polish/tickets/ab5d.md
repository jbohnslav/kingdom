---
id: "ab5d"
status: closed
deps: []
links: []
created: 2026-02-16T11:54:37Z
type: task
priority: 2
---
# @mentions should autocomplete (tab-complete) and render in the member's color

## Acceptance Criteria

- [x] Tab-completion for @mentions in the chat TUI input area
- [x] @mentions rendered in member brand colors in all message panels
- [x] Cycling through multiple matches with repeated Tab
- [x] Tests for tab-completion and colored mention rendering

## Work Log

### Tab-completion for @mentions (InputArea)
- Added `member_names` parameter to `InputArea.__init__()` so it knows which names to complete
- On Tab key: finds `@partial` token at cursor position using regex, matches against member names + "all"
- First Tab: replaces `@partial` with `@completedname ` (with trailing space)
- Repeated Tab: cycles through all matching candidates
- Non-tab keypress resets completion state
- `ChatApp.compose()` passes `member_names` to `InputArea`

### Colored @mentions (ColoredMentionMarkdown)
- New `ColoredMentionMarkdown` class in `widgets.py` — a Rich renderable that wraps `RichMarkdown`
- Intercepts rendered `Segment` objects and splits those containing `@member` tokens
- Applies the member's brand color (from `color_for_member()`) + bold style to @mention segments
- Also colors `@all` and `@king` (white bold)
- `MessagePanel` now accepts optional `member_names` and uses `ColoredMentionMarkdown` when available
- All three `MessagePanel` construction sites in `app.py` updated to pass `member_names`

### Pre-existing fix: Cursor stream extractors
- Added `extract_cursor_stream_text()` for Cursor assistant + result events
- Added `extract_cursor_stream_thinking()` for Cursor thinking delta events
- Restored `merge_assistant_snapshots` call in `tail_stream_file` for cursor backend
- Fixed pre-existing test failures in `test_tui_poll.py`
