---
id: kin-08da
status: closed
deps: [kin-896d]
links: []
created: 2026-02-05T03:12:14Z
type: task
priority: 2
---
# Remove old breakdown.md infrastructure

Clean up the old breakdown.md parsing code now that agents create tickets directly.

Remove:
- parse_breakdown_tickets() from breakdown.py
- build_breakdown_template() from breakdown.py
- breakdown.md references from state management
- Any other breakdown.md related code

Update:
- kd status to reflect new flow (no breakdown.md step)
- state.json schema: remove breakdown_path field, add tickets_created_at timestamp

Acceptance criteria:
- [x] No references to breakdown.md parsing remain
- [x] kd status shows correct workflow state
- [x] Existing functionality not broken

## Work Log

### Implementation (2026-02-04)

**Removed:**
- Entire `breakdown.py` module (template, parsing, council prompts)
- `tests/test_breakdown.py` test file
- `breakdown_path` from `_get_branch_paths()` return value
- `breakdown_status` from `kd status` output

**Updated:**
- `_get_branch_paths()` now returns 3-tuple instead of 4-tuple
- `kd status` no longer shows "Breakdown: present/empty" line
- Status help text updated

**Note:** Did not add `tickets_created_at` timestamp - the agent-driven flow creates tickets directly with their own timestamps, making this redundant.

**Commit:** 5c0e215
