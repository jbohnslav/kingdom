# Design: Breakdown Stage Improvement

## Goal

Eliminate the fragile intermediate `breakdown.md` format by having `kd breakdown` invoke an agent that creates tickets directly from the design document using existing CLI commands.

## Context

The breakdown stage is the critical bridge between design and execution. Currently it has significant friction.

### The Problem

**Current flow**:
```
design.md → breakdown.md (rigid markdown) → kin-*.md (structured tickets)
```

The intermediate `breakdown.md` requires a specific format that agents struggle to produce:
- `parse_breakdown_tickets()` uses regex: `^- \[[ xX]\] (?P<id>[^:]+): (?P<title>.+)$`
- Requires exact 2-space indentation for metadata lines
- No validation or error feedback when format doesn't match
- `kd breakdown --apply` silently creates zero tickets if parsing fails

But agents naturally write markdown with headers and bold text, not rigid checkbox lists. Fighting this is a losing battle.

### The Insight

Why parse rigid markdown to create structured files? The intermediate format exists because of tooling limitations, not workflow needs. If an agent can create tickets directly, we eliminate the parsing problem entirely.

**Key realization**: We already have the infrastructure for this:
- Agent invocation exists (Council system)
- `kd ticket create <title> -d <desc> -p <priority>` CLI exists
- `kd ticket dep <id1> <id2>` for dependencies exists
- SKILL.md already teaches agents how to use the CLI

We don't need custom tools—just invoke an agent with the right prompt.

### Proposed Flow

```
design.md (with Breakdown section) → agent runs CLI commands → kin-*.md (structured tickets)
```

The design doc includes a freeform "Breakdown" section (rough groupings, natural prose). When ready, `kd breakdown` invokes an agent that reads the design and creates tickets using existing `kd ticket` CLI commands.

## Requirements

1. **Agent-driven ticket creation**: `kd breakdown` invokes an agent to create tickets from the design doc
2. **Use existing CLI**: Agent uses `kd ticket create` and `kd ticket dep` commands (no custom tools)
3. **Preview before commit**: `--dry-run` has agent output planned commands without executing
4. **Confirmation**: Require confirmation before agent executes commands (skip with `--yes`)
5. **Single agent invocation**: Add `--agent <name>` flag to run one council member instead of all 3
6. **Idempotency handling**: Clear behavior when run multiple times (skip existing, error, or overwrite)

## Non-Goals

- Keeping `breakdown.md` as a required artifact
- Custom `create_ticket` tool infrastructure (use existing CLI)
- Automated design-to-breakdown (the Breakdown section is still human/agent authored in design phase)

## Decisions

### 1. Eliminate breakdown.md

**Decision**: Remove `breakdown.md` as a required intermediate artifact.

**Rationale**: It exists to solve a tooling problem (CLI needs structured input), not a workflow need. Council unanimously agreed this is the right call.

**What we preserve**:
- Reviewable plan → freeform Breakdown section in design.md
- Checkpoint before tickets → preview + confirmation in `kd breakdown`

### 2. Repurpose `kd breakdown` Command

**Decision**: `kd breakdown` becomes "read design, invoke agent, create tickets via CLI."

**Rationale**:
- Preserves the mental model (init → design → breakdown → work)
- Command name still makes sense ("breaking down" design into tickets)
- Muscle memory and docs already point here

**New behavior**:
```
kd breakdown [--dry-run] [--yes] [--agent <name>]
```
1. Reads design.md (including Breakdown section)
2. Invokes agent with prompt: "Create tickets from this design using `kd ticket create` and `kd ticket dep`"
3. `--dry-run`: Agent outputs planned commands without executing
4. Default: Agent executes commands after confirmation (skip with `--yes`)

### 3. Use Existing CLI Commands (No Custom Tools)

**Decision**: Agent uses existing `kd ticket create` and `kd ticket dep` commands.

**Rationale** (from council review):
- Infrastructure already exists and is battle-tested
- SKILL.md already teaches agents how to use the CLI
- Avoids building bespoke parsing/tool infrastructure
- Agent runners (Claude, etc.) already handle shell command execution

**Safety considerations**:
- Prompt explicitly constrains agent to only `kd ticket` commands
- Consider command allow-list in agent runner for this mode
- Log all commands and outputs for audit/debugging
- Stop on first error with clear summary

### 4. Single Agent Invocation

**Decision**: Add `--agent <name>` flag to run one council member instead of all 3.

**Rationale**:
- Faster and more predictable for ticket creation
- Full council (3 agents) is overkill for this task
- Default to Claude, allow override

### 5. Design Doc Template Update

**Decision**: Update design template to include Breakdown section guidance.

**Rationale**: The Breakdown section replaces `breakdown.md` as the human-readable execution plan.

**Template addition**:
```markdown
## Breakdown

<!--
Add this section when the design is solidified.
Describe how to break the work into tickets - rough groupings,
key phases, dependencies. This doesn't need rigid formatting;
the agent will interpret it when creating tickets.
-->
```

## Technical Approach

### CLI Changes (cli.py)

Refactor `kd breakdown` command:

1. Remove `--apply` flag (agent execution is the default behavior)
2. Add `--dry-run` flag (agent outputs planned commands, doesn't execute)
3. Add `--yes` flag (skip confirmation prompt)
4. Add `--agent <name>` flag (run single council member, default: claude)
5. Remove breakdown.md template generation
6. Add design doc validation (must have Breakdown section)

### Agent Invocation

Build a prompt that includes:
1. The design doc content (especially the Breakdown section)
2. CLI reference from SKILL.md (or inline instructions for `kd ticket create` and `kd ticket dep`)
3. Clear instructions: "Create tickets from the Breakdown section. Use `kd ticket create` for each ticket, then `kd ticket dep` to wire dependencies."

For `--dry-run`: Instruct agent to output the commands it would run without executing them.

### Council Infrastructure (council/)

Add single-member invocation:
1. Add `query_single(member_name: str, prompt: str)` method to Council class
2. Or add `--agent <name>` flag to `kd council ask` command
3. Reuse existing session management and logging

### Cleanup

1. Remove `parse_breakdown_tickets()` from breakdown.py
2. Remove `build_breakdown_template()`
3. Remove breakdown.md references from state management
4. Update SKILL.md to remove breakdown.md format guidance

### State Changes

Update `state.json` schema:
- Remove `breakdown_path` field
- Add `tickets_created_at` timestamp
- Keep design doc reference

## Open Questions

1. **What if design has no Breakdown section?** Error with guidance, or prompt agent to suggest one?

2. **Re-running after tickets exist?** Options: skip existing IDs, error, or `--force` to overwrite. Leaning toward skip + warn.

3. **Error handling**: If agent fails halfway through creating tickets, what's the rollback story? Likely: stop on first error, print summary of what was created.

## Success Criteria

- `kd breakdown` creates valid tickets from a design doc on first try
- No rigid markdown format for users/agents to learn
- Clear preview with `--dry-run` before any tickets are created
- Tickets have correct dependencies wired up
- Running twice doesn't duplicate tickets

---

## Breakdown

### Phase 1: Single Agent Invocation

**Add `--agent` flag to council infrastructure**
- Add `query_single(member_name: str, prompt: str)` to Council class, or
- Add `--agent <name>` flag to `kd council ask` command
- Reuse existing session management and logging

**Dependencies**: None - this enables the rest

### Phase 2: CLI Refactor

**Update `kd breakdown` command**
- Remove `--apply` flag, make agent-driven ticket creation the default
- Add `--dry-run` for preview-only mode (agent outputs commands without executing)
- Add `--yes` to skip confirmation prompt
- Add `--agent <name>` to select which council member to use (default: claude)
- Read design doc, validate Breakdown section exists
- Build prompt with design doc + CLI instructions
- Invoke agent, display output

**Dependencies**: Phase 1 (needs single-agent invocation)

### Phase 3: Cleanup

**Remove old breakdown.md infrastructure**
- Remove `parse_breakdown_tickets()` and related parsing code
- Remove `build_breakdown_template()`
- Remove breakdown.md from state tracking
- Update `kd status` to reflect new flow

**Dependencies**: Phase 2 (old code shouldn't be removed until new flow works)

### Phase 4: Documentation

**Update docs and skill**
- Update SKILL.md: remove breakdown.md format, add Breakdown section guidance
- Update design doc template with Breakdown section placeholder
- Update any references in ARCHITECTURE.md or other docs

**Dependencies**: Phase 3 (docs should reflect final state)
