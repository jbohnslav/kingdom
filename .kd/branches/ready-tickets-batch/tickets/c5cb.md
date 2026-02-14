---
id: c5cb
status: closed
deps: []
links: []
created: 2026-02-13T22:47:40Z
type: feature
priority: 1
---
# Replace kd breakdown with agent prompt output

Strip the current breakdown command of all its ticket-parsing/creation logic (parse_breakdown_tickets, --apply, the two-pass create+link algorithm, etc). Instead, kd breakdown should just print a ready-to-paste prompt for a coding agent (Claude Code, Cursor, etc). The prompt should instruct the agent to: read the design doc, use kd tk create/dep CLI commands to turn it into tickets with proper dependencies. This removes a bunch of fragile markdown parsing and leverages the agent to do the smart work. Clean up breakdown.py of unused code (parse_breakdown_tickets, council prompt builders, etc) and remove related tests.

## Implementation Notes (council)

**Key files:** `src/kingdom/cli.py` (breakdown command ~L829-907), `src/kingdom/breakdown.py`

**Approach:**
- Gut the current `breakdown()` command body — remove `--apply` flag, `parse_breakdown_tickets()`, the two-pass create+link algorithm, and `state.json` mapping logic
- Replace with a function that reads design.md, builds a prompt instructing an agent to use `kd tk create` and `kd tk dep`, and prints to stdout
- Delete `parse_breakdown_tickets()` and related helpers from `breakdown.py`
- Remove related tests

**Gotchas:**
- `build_breakdown_template()` may still be useful for the prompt — evaluate before deleting
- Grep for anything importing `parse_breakdown_tickets`
- The `state.json` breakdown_id → ticket_id mapping can be removed if nothing reads it downstream
- Don't break `design_show()` or `design_approve()` which share `get_branch_paths()`
- Do this before 3860 (config file) so config doesn't need a breakdown prompt section

## Worklog

- Rewrote `breakdown()` CLI command: removed `--apply` flag, `parse_breakdown_tickets` import, two-pass create+link, state.json mapping
- New command reads design.md and prints an agent-ready prompt with instructions to use `kd tk create` and `kd tk dep`
- Includes relative path to design doc in the prompt
- Cleaned `breakdown.py`: removed `parse_breakdown_tickets`, `build_breakdown_council_prompt`, `build_breakdown_update_prompt`, `extract_tagged_block`, `parse_breakdown_update_response`, `BreakdownUpdate`, `AgentResponse` import
- Kept `build_breakdown_template`, `read_breakdown`, `write_breakdown`, `ensure_breakdown_initialized`
- Updated tests: removed `parse_breakdown_tickets` test, updated CLI test assertions
- 483 tests pass (3 fewer — removed tests for deleted functions)
