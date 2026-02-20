---
id: "bec3"
status: closed
deps: []
links: []
created: 2026-02-17T17:31:29Z
type: task
priority: 2
assignee: peasant-bec3
---
# in_review ticket status + CLI compatibility

## Description

Add `in_review` to the ticket status model. Ticket lifecycle becomes: `open → in_progress → in_review → closed`.

Update all CLI commands that reference ticket status:
- `kd status`: include `in_review` as its own count bucket
- `kd tk list`: display `in_review` tickets; accept `--status in_review` filter
- `kd tk current`: returns `in_progress` only (exclude `in_review`)
- `kd tk ready`: excludes `in_review` (not dispatchable)
- `kd peasant start`: if ticket is `open`, set to `in_progress`; cannot start on `in_review`

Transition rules: `open → in_progress` on `kd peasant start`.

## Acceptance Criteria

- [x] `in_review` added to `STATUSES` in `ticket.py`
- [x] `kd tk list` shows `in_review` tickets with distinct styling
- [x] `kd tk list --status in_review` filters correctly
- [x] `kd status` counts `in_review` separately
- [x] `kd tk current` excludes `in_review`
- [x] `kd tk ready` excludes `in_review`
- [x] `kd peasant start` blocks on `in_review` tickets
- [x] Tests pass

## Worklog

- [18:45] Using the `kingdom` skill for this ticket because this is `kd` workflow and ticket-state CLI behavior work. I’ll read the skill instructions and the ticket file first, then patch code and tests, run validation, and commit.
I have the ticket requirements and now I’m mapping where status values are...
- [18:53] Continued on top of the interrupted peasant diff, fixed one failing peasant test for hand-mode transition behavior, then ran targeted tests and the full suite (`1106 passed, 29 skipped, 1 xfailed`). Manually checked `kd status`, `kd tk list`, `kd tk list --status in_review`, `kd tk current`, `kd tk ready`, and `kd peasant start rev1 --hand` in a temp repo to verify `in_review` behavior.
- [18:49] Proceeding on top of the existing worktree edits from the earlier run. I’m inspecting the current diffs and tests first, then I’ll patch any gaps, run validation (including manual CLI checks), and commit.
I found that most of the ticket changes already exist in the interrupted diff; next I’m revi...
- [18:49] Quality gates passed (pytest + ruff) — marking done
