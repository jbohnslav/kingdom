---
from: codex
to: king
timestamp: 2026-02-14T14:07:25Z
---

Using the `kingdom` skill for this design-phase pass; I’ll read the updated design doc fresh and give a readiness assessment with any remaining implementation blockers or risks.
I found the updated doc and it’s much tighter. I’m doing one quick code cross-check for hidden implementation traps (especially `.kd/.gitignore`, prompt merge points, and shared frontmatter parsing usage) before giving a final go/no-go assessment.
Not quite ready yet. It’s much better than prior pass, but I’d block implementation on a few remaining issues.

1. **Missing `extra_params` despite prior decision to include it**
The design only specifies `extra_flags` in requirements/schema (`.kd/branches/config-system/design.md:24`, `.kd/branches/config-system/design.md:88`, `.kd/branches/config-system/design.md:127`). If the King’s decision is “extra_params/extra_flags escape hatch,” the schema is incomplete.

2. **`.kd/config.json` conflicts with current `.kd/.gitignore` defaults**
Current base layout ignores `*.json` under `.kd` (`src/kingdom/state.py:217`), which includes `.kd/config.json`. If config is meant to be shared/project-level, this will silently keep it untracked unless you add an explicit unignore rule. The design doesn’t address this (`.kd/branches/config-system/design.md:20`, `.kd/branches/config-system/design.md:122`).

3. **One implementation note is unsafe: `parse_frontmatter()` removal**
Design suggests removing it if no longer used (`.kd/branches/config-system/design.md:184`), but it is still used by tickets and threads (`src/kingdom/thread.py:30`, `src/kingdom/ticket.py:32`). This will break unrelated core flows if removed.

4. **Prompt semantics still need tighter phase mapping**
You define per-phase prompts and merge order (`.kd/branches/config-system/design.md:87`, `.kd/branches/config-system/design.md:101`), but not a strict command-to-phase map (for example exactly where `review` applies vs peasant loop vs council ask). Without this, implementations will diverge.

5. **Timeout precedence is underspecified**
You now have role timeouts (`.kd/branches/config-system/design.md:68`, `.kd/branches/config-system/design.md:72`) but no precedence rules against CLI flags like `kd council ask --timeout` (current behavior in `src/kingdom/cli.py:302`). Define one precedence rule now.

6. **`extra_flags` needs guardrails**
Given read-only council guarantees, arbitrary flags can still undermine policy if injected carelessly (`.kd/branches/config-system/design.md:127`). Keep the escape hatch, but define where flags are injected and what cannot be overridden.

7. **No schema version is workable now but increases migration risk**
You explicitly defer versioning (`.kd/branches/config-system/design.md:36`). It’s not fatal, but it’s cheap to add now and avoids future ambiguity.

**Go/No-Go:** **No-go until #1–#3 are fixed.**
After that, it’s implementable with moderate risk; #4–#6 should be clarified before coding to avoid churn.
