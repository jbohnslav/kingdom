---
id: "aad9"
status: closed
deps: []
links: []
created: 2026-02-17T03:15:56Z
type: task
priority: 2
---
# kd chat: replace WaitingPanel with Textual LoadingIndicator for animated feedback

From audit: docs/chat-tui-polish-audit.md (ticket 8dea).

Current WaitingPanel is a static 1-height dashed box with "member -- waiting..." text. Council queries can take minutes, and there is no animation to signal the app is alive.

Textual provides a built-in `LoadingIndicator` widget with pulsating dots animation.

## Acceptance Criteria

- [x] WaitingPanel uses Textual's LoadingIndicator or equivalent animated feedback
- [x] Member name and "waiting" label remain visible
- [x] Colored border per member is preserved
- [x] Existing tests pass; WaitingPanel tests updated for new widget
- [x] Quick win: estimated ~30 min

## Worklog

- Changed WaitingPanel base class from Static to Widget, added compose() yielding LoadingIndicator
- Height bumped from 1 to 3 to fit animation within border
- Border title and per-member color preserved
- 1 new test (composes_loading_indicator); full suite: 1255 passed
