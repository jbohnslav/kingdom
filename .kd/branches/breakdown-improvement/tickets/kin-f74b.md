---
id: kin-f74b
status: closed
deps: [kin-08da]
links: []
created: 2026-02-05T03:12:16Z
type: task
priority: 2
---
# Update docs for new breakdown flow

Update documentation to reflect the simplified agent-driven breakdown flow.

Updates needed:
- SKILL.md: Remove breakdown.md format guidance, add Breakdown section guidance
- Design doc template: Add Breakdown section placeholder with comment explaining usage
- ARCHITECTURE.md or other docs: Update any references to breakdown.md

Acceptance criteria:
- [x] SKILL.md teaches agents to write freeform Breakdown sections
- [x] Design template includes Breakdown section guidance
- [x] No stale references to breakdown.md format

## Work Log

### Implementation (2026-02-04)

**Updated files:**
- `SKILL.md` - Updated breakdown phase docs, key directories section
- `docs/cli-skill-architecture.md` - Major update:
  - Changed directory structure from `runs/` to `branches/`
  - Removed all breakdown.md references
  - Updated kd breakdown command docs
  - Fixed ASCII diagrams and tables
- `docs/council-design.md` - Updated directory structure

**Note:** docs/archive/ files were left unchanged as they're historical records. The only remaining "breakdown.md" references in the codebase are in archived documentation.

**Commit:** a56ad62
