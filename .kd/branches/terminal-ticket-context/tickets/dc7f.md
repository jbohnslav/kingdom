---
id: "dc7f"
status: closed
deps: []
links: []
created: 2026-07-05T02:30:23Z
type: bug
priority: 2
closed_at: 2026-07-05T02:37:51Z
assignee: hand
---
# Record archived branch ticket location in terminal context

Claude re-review found terminal_context_location_for_start falls back to branch:<current> for tickets resolved from .kd/archive/<branch>/tickets. The Stop hook already understands archive:<name>, so kd tk start should record archive:<branch> when starting an archived non-backlog branch ticket instead of recording the current active branch.

## Acceptance Criteria

- [x] Starting an archived non-backlog branch ticket records archive:<branch> location
- [x] Stop hook can validate terminal context for archived branch ticket location
- [x] Regression test covers archived branch ticket start location

## Worklog

- 2026-07-05: Started from Claude re-review finding. terminal_context_location_for_start already records backlog and branch locations, and the Stop hook already understands archive:<name>, but start falls back to the current branch for tickets found under .kd/archive/<branch>/tickets.
- 2026-07-05: Added failing regression for starting a ticket from .kd/archive/old-feature/tickets and expecting terminal context location archive:old-feature. Added Stop hook coverage proving archive:<name> terminal context validates against archived branch tickets. Updated terminal_context_location_for_start to recognize archive/<branch>/tickets before falling back to current branch.
- 2026-07-05: Verification passed: uv run pytest tests/test_cli_ticket_lifecycle.py::TestTicketCloseArchive::test_start_records_archived_branch_terminal_ticket_context_location tests/test_hook.py::TestStopHandler::test_prefers_started_archived_branch_ticket_context -q; uv run ruff check; uv run pytest -q with 1920 passed, 38 skipped, 1 xfailed.
