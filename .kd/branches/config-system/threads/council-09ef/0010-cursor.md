---
from: cursor
to: king
timestamp: 2026-02-14T13:32:05Z
---

Here is a critical review of the design document at `.kd/branches/config-system/design.md`.

### 1. Location Inconsistency
**Critique**: The doc proposes `kingdom.json` at the **project root**. This breaks the established pattern that "Kingdom state lives in `.kd/`".
**Risk**: Clutters the user's root directory. Users already have `package.json`, `tsconfig.json`, `pyproject.toml`, etc. Adding `kingdom.json` might be annoying.
**Recommendation**: Move it to `.kd/config.json`. This keeps the root clean and groups all Kingdom artifacts together.

### 2. The "Inline Prompts" Decision
**Critique**: The doc explicitly rejects `prompt_file` ("Inline prompts only... If long prompts become a real need, `prompt_file` is a backwards-compatible addition later").
**Risk**: You specifically asked about long/multiline prompts. JSON strings with `\n` are painful to edit for anything longer than two sentences. Users *will* want to paste entire "persona" documents.
**Recommendation**: Add `system_prompt_file` (or `prompt_file`) to the schema **now**. It costs very little to implement (`Path(file).read_text()`) and solves the "JSON is awkward for text" problem immediately.

### 3. Schema: Defaults Merging Strategy
**Critique**: The doc says "defaults preserved for backward compatibility" but doesn't define the **merge strategy**.
**Risk**: If I define `"agents": { "claude": { "timeout": 999 } }`, does it:
   a) **Replace** the entire default "claude" agent (losing the backend/cli defaults)?
   b) **Merge** into the default "claude" agent?
**Recommendation**: Explicitly state that the config is a **deep merge** over the internal defaults. Users shouldn't have to re-specify `backend: "claude_code"` just to change a timeout.

### 4. Schema: `extra_flags` vs `args`
**Critique**: `extra_flags` is a bit specific.
**Recommendation**: Rename to `extra_args` to align with standard CLI terminology (arguments vs flags).

### 5. Implementation: Validation
**Critique**: "Dataclasses with manual validation" is fine, but the doc is vague on *when* validation happens.
**Risk**: If validation happens only when the agent is *used*, the user might not know their config is broken until a specific workflow triggers.
**Recommendation**: Run full config validation eagerly on **every** `kd` command startup. Fail fast if `kingdom.json` is invalid.

### 6. Missing: `kd config init` Behavior
**Critique**: The doc mentions `kd config init` scaffolds defaults.
**Risk**: Does it overwrite? Does it dump *all* defaults (making the file huge) or just a minimal skeleton?
**Recommendation**: `kd config init` should dump a **minimal** skeleton (comments if JSONC were supported, but standard JSON doesn't support comments, which is another downside of JSON for config). It should probably dump a "Council of Three" example so users see how to configure it.

### Summary of Recommendations

1.  **Move** file to `.kd/config.json`.
2.  **Add** `prompt_file` support immediately.
3.  **Define** merge strategy (Deep Merge).
4.  **Rename** `extra_flags` to `extra_args`.
5.  **Validate** eagerly on app startup.
