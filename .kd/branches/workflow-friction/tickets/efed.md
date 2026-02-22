---
id: "efed"
status: closed
deps: []
links: []
created: 2026-02-14T15:57:21Z
type: task
priority: 2
---
# kd commands should auto-detect active session from branch name without requiring kd start

## Acceptance Criteria

- [x] `resolve_current_run()` falls back to git branch detection when `.kd/current` is missing
- [x] If current git branch has a matching `.kd/branches/<normalized>/` directory, use it
- [x] If no match, original error message is preserved
- [x] Detached HEAD gracefully falls through to original error
- [x] Tests cover: branch match found, no match, detached HEAD, current file still takes priority
- [x] Manual verification: `rm .kd/current && kd tk list` works without `kd start`

## Worklog

- Moved `get_current_git_branch()` from cli.py to state.py (needed by resolve_current_run)
- Added 3-tier resolution: explicit .kd/current → git branch match → error
- 9 new tests in test_state.py (TestResolveCurrentRun)
- Full suite green: 1239 passed
- Manual verification: removed .kd/current, `kd tk list` auto-detected workflow-friction branch
- [16:42] — Closed: All acceptance criteria met, tests passing
