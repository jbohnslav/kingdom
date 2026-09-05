---
id: "fbe2"
status: closed
deps: []
links: []
created: 2026-09-05T18:49:50Z
type: task
priority: 2
closed_at: 2026-09-05T18:52:15Z
resolution: completed
close_reason: "Reject every ambiguous matching path and report candidate boards, titles, and paths; regression and full suite pass"
closed_context: codex:1fd7693df963292c
assignee: codex:1fd7693df963292c
---
# Reject ambiguous ticket IDs across boards

From the 2026-09-02 Kingdom skill feedback: duplicate short IDs across branches can silently resolve to an unrelated ticket. Replace location preference with explicit ambiguity errors listing each candidate board, title, and path. Preserve safe unique-prefix lookup.

## Acceptance Criteria

- [x] Failing regression proves collisions cannot silently select or mutate a ticket
- [x] Ambiguity errors identify all candidate boards and titles
- [x] Full test suite and manual CLI checks pass

## Worklog

- [2026-09-05 14:50] [codex:1fd7693d] — Root cause: find_ticket deduplicates by frontmatter ID before checking ambiguity, deliberately preferring the current branch. Earlier tickets aa61/4784 introduced that policy; this report supersedes it for ID lookup. Keep collection behavior outside this ticket; make lookup refuse every distinct matching path, with board/title/path evidence.
- [2026-09-05 14:51] [codex:1fd7693d] — Red phase: 38 regressions failed because lookup selected one copy (including close/defer mutation cases). Green phase: 178 passed, 3 skipped across ticket and collision tests. Lookup now checks every matching path, with deterministic board/title/path diagnostics. Manually invoked uv run kd tk find 2a92 in a disposable fixture and inspected the two-candidate error. Ruff fixed an obsolete test import and formatting; full suite running.
- [2026-09-05 14:52] [codex:1fd7693d] — Full verification: uv run pytest -q passed (2320 passed, 49 skipped, 1 xfailed). Existing explicit branch-scoped callers retain their search scope; bare-ID reads and mutations no longer silently prefer a board. No implementation failures remain.
- [14:52] [codex:1fd7693df963292c] — Closed: Reject every ambiguous matching path and report candidate boards, titles, and paths; regression and full suite pass

## Lifecycle

- 2026-09-05T18:52:15Z [codex:1fd7693df963292c] — closed (completed): Reject every ambiguous matching path and report candidate boards, titles, and paths; regression and full suite pass
