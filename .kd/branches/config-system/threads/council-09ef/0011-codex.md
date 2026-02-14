---
from: codex
to: king
timestamp: 2026-02-14T13:32:38Z
---

Using the `kingdom` skill for this review because this is a `kd` design-phase artifact. I’ll read `.kd/branches/config-system/design.md` and return a critical findings-first review with concrete risks and recommendations.
**Findings (ordered by severity)**

1. **Missing per-phase prompt config despite stated need**
`design.md` says config should cover prompts, but schema only has one agent-level `prompt` (`.kd/branches/config-system/design.md:20`, `.kd/branches/config-system/design.md:74`). Ticket 3860 explicitly asks for prompts varying by workflow phase (ask/design/review). Current design can’t express that.

2. **`extra_flags` conflicts with “CLI details stay in code” and creates safety bypass risk**
You say CLI invocation details are code-owned (`.kd/branches/config-system/design.md:25`), but `extra_flags` allows users to alter invocation behavior anyway (`.kd/branches/config-system/design.md:23`, `.kd/branches/config-system/design.md:99`). This can accidentally or intentionally bypass council read-only constraints.

3. **Timeout schema/precedence is underspecified and likely to produce inconsistent behavior**
You have `agent.timeout`, `council.timeout`, `peasant.timeout` (`.kd/branches/config-system/design.md:58`, `.kd/branches/config-system/design.md:62`, `.kd/branches/config-system/design.md:76`) but no precedence rules or interaction with CLI `--timeout`. This will cause confusing runtime outcomes.

4. **No migration path is risky for a broad refactor**
“Remove all agent file code” + “no migration needed” (`.kd/branches/config-system/design.md:117`, `.kd/branches/config-system/design.md:133`) is brittle. Even if adoption is low, this is a wide blast radius and can break existing setups/tests unexpectedly.

5. **Role model is incomplete**
You configure council and peasant, but not hand/default advisor role assignment (`.kd/branches/config-system/design.md:56`, `.kd/branches/config-system/design.md:60`). The stated goal is role composition; this only partially addresses it.

6. **Validation policy is too permissive for manual validation**
“Unknown keys warn and ignore” (`.kd/branches/config-system/design.md:112`, `.kd/branches/config-system/design.md:137`) will hide typos in JSON. With manual validation, fail-fast is safer and easier to debug.

7. **Schema versioning missing**
No explicit top-level `version` field in example (`.kd/branches/config-system/design.md:38`). Without it, future schema evolution/migration is harder.

8. **Potential over-scope for one ticket**
This design combines config system, agent model replacement, council wiring, peasant wiring, state cleanup, and new `kd config` CLI (`.kd/branches/config-system/design.md:106`, `.kd/branches/config-system/design.md:117`, `.kd/branches/config-system/design.md:125`). That’s a lot for one change-set and increases regression risk.

**Recommendations**

1. Add explicit phase prompts in schema now (`council.ask`, `design`, `review`, optionally `peasant.loop`) and define merge order.
2. Keep `extra_flags` but constrain it: role-aware allowlist and/or backend-specific injection points so read-only council protections cannot be disabled.
3. Define timeout precedence in doc: CLI flag > per-role > per-agent > default, with clear semantics per command path.
4. Add `version: 1` to config and strict validation by default (unknown keys error).
5. Do a short compatibility window for `.kd/agents/*.md` reading (read-only fallback) before full removal.
6. Consider splitting delivery:
   1. v1: load/validate JSON + council/peasant selection + prompt/timeouts.
   2. v1.1: remove legacy agent-file plumbing + add `kd config` UX polish.

Overall direction is solid and pragmatic, but the current doc under-specifies prompt phases and safety boundaries, and over-combines risky refactors into one step.
