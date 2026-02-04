---
id: kin-a8ac
status: closed
deps: [kin-c039]
links: []
created: 2026-02-04T21:22:45Z
type: task
priority: 1
assignee: Jim Robinson-Bohnslav
---
# Update kd done command

Move .kd/branches/<name>/ to .kd/archive/<name>/. Clear .kd/current. Update state.json with done_at and status. Clean up associated worktrees. Handle archive collision with timestamp suffix.

## Acceptance Criteria

- [x] kd done moves branch folder to archive
- [x] .kd/current is cleared
- [x] Archived folder preserves all content
- [x] Worktrees cleaned up
- [x] Handles archive collision (adds suffix)

## Work Log

### 2026-02-04
- Updated `resolve_current_run` in `state.py` to check branches/ first, then fall back to legacy runs/
- Rewrote `done` command in `cli.py` to:
  - Move branch folder from `.kd/branches/<name>` to `.kd/archive/<name>`
  - Handle archive collision by adding timestamp suffix (e.g., `feature-20260204T163045`)
  - Clean up associated worktrees via `git worktree remove --force`
  - Clear `.kd/current` when archiving current branch
  - Support legacy runs/ structure for backwards compatibility
- Updated all tests in `test_done.py` to use new branch-based structure
- Added tests for archive collision handling and legacy runs compatibility
- All 8 tests passing

