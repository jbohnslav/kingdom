---
id: kin-896d
status: closed
deps: [kin-a8d9]
links: []
created: 2026-02-05T03:12:11Z
type: task
priority: 1
---
# Refactor kd breakdown to invoke agent

Update kd breakdown command to invoke an agent that creates tickets via CLI.

Changes:
- Remove --apply flag (agent execution is the default behavior)
- Add --dry-run flag (agent outputs planned commands, doesn't execute)
- Add --yes flag (skip confirmation prompt)
- Add --agent <name> flag (run single council member, default: claude)
- Remove breakdown.md template generation
- Validate design doc has Breakdown section

Build prompt that includes:
- Design doc content (especially Breakdown section)
- CLI instructions for kd ticket create and kd ticket dep
- Clear instructions to create tickets from the Breakdown section

Acceptance criteria:
- [x] kd breakdown invokes agent and creates tickets from design doc
- [x] --dry-run shows planned commands without executing
- [x] --yes skips confirmation
- [x] Prompt constrains agent to only kd ticket commands

## Work Log

### Implementation (2026-02-04)

**Approach:**
1. Added `_extract_breakdown_section()` helper to parse `## Breakdown` from design docs
2. Added `_build_breakdown_prompt()` to construct agent prompt with CLI instructions
3. Rewrote `breakdown()` command with new flags and agent invocation

**Key decisions:**
- Prompt explicitly lists only `kd ticket create` and `kd ticket dep` as allowed commands
- Design doc must have `## Breakdown` section (clear error message if missing)
- Default agent is "claude" - same as council ask default
- 5 minute timeout for agent (longer than default 2 min since creating multiple tickets)
- Confirmation shows the Breakdown section content before proceeding

**Files changed:**
- `src/kingdom/cli.py` - New breakdown command with agent invocation
- `src/kingdom/design.py` - Added Breakdown section to design template
- `tests/test_cli_design_breakdown.py` - Updated tests for new behavior
- `SKILL.md` - Updated documentation for new workflow

**Commit:** e0ac1da
