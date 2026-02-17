---
id: "aad9"
status: open
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

- [ ] WaitingPanel uses Textual's LoadingIndicator or equivalent animated feedback
- [ ] Member name and "waiting" label remain visible
- [ ] Colored border per member is preserved
- [ ] Existing tests pass; WaitingPanel tests updated for new widget
- [ ] Quick win: estimated ~30 min
