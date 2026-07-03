---
id: "4fda"
status: closed
deps: []
links: []
created: 2026-07-03T15:21:40Z
type: feature
priority: 2
closed_at: 2026-07-03T15:45:43Z
---
# List recently closed tickets

It is hard to inspect recently completed work. Add a way to list or filter recently closed tickets, ideally using existing tk list patterns so users can quickly review what was closed most recently.

## Acceptance Criteria

- [x] Users can list closed tickets ordered by most recent closure
- [x] Users can limit the number of recently closed tickets shown
- [x] Tests cover recently closed listing/filtering

## Worklog

- [2026-07-03 11:44] — Implemented recently closed ticket listing.

  Details:
  - Added kd tk list --recently-closed/--recent to show closed tickets sorted by closed_at descending.
  - Added --limit/-n to cap displayed rows after filtering.
  - --all --recently-closed includes archived tickets so closed backlog work can be found.

  Verification: focused recently-closed list tests pass.
- [11:45] — Closed: Added kd tk list --recently-closed/--recent plus --limit/-n. Verified with focused recently-closed tests, full ticket-list tests, manual CLI output checks, ruff, and full uv run pytest.
- [2026-07-03 11:57] — Council review attempted in thread council-885a.

  Result: no actionable council review was produced. Claude returned a usage-limit message (resets 3:30pm America/New_York). Codex failed twice before responding due an MCP tool conversion error for playwright__browser_drop. Current configured council members are claude and codex only.
- [2026-07-03 13:46] — Addressed Codex council findings: --recently-closed now has explicit empty-state messages instead of claiming no tickets exist, and --backlog --recently-closed --json preserves archive:backlog location labels for archived backlog tickets. Added regression tests for both cases and manually checked recent list output plus backlog recent JSON.
