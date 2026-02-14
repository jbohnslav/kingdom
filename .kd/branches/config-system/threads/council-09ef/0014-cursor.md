---
from: cursor
to: king
timestamp: 2026-02-14T14:06:41Z
---

The design doc is **mostly ready**, but I have three specific recommendations to address before implementation.

### 1. Path Resolution for `system_prompt_file`
You added `system_prompt_file` support (good!), but the doc doesn't specify how relative paths are resolved.
*   **Risk**: Users will assume it's relative to the project root, or relative to `.kd/`. Ambiguity leads to "File not found" errors.
*   **Recommendation**: Explicitly state that `system_prompt_file` is **relative to the `.kd/` directory**.
    *   Example: `"system_prompt_file": "prompts/critic.md"` resolves to `.kd/prompts/critic.md`.

### 2. Prompt Composition Strategy
The doc says: *"Prompt merge order: safety preamble (hardcoded) + phase prompt + agent prompt + user prompt."*
*   **Issue**: This means the user cannot *replace* the safety preamble if they want to.
*   **Recommendation**: Keep the additive behavior as default, but consider if `system_prompt` should *replace* the agent's default persona if one exists in the backend code (though currently backends don't seem to have inherent personas, only the Council preamble).
*   **Clarification**: Ensure `agent.py` builders handle this concatenation cleanly with newlines.

### 3. Model Flag Mapping
The doc says: *"Model identifier (code translates to the right CLI flag per backend)"*.
*   **Gap**: You need to ensure the `agent.py` command builders actually implement this translation.
    *   **Claude**: `["--model", config.model]`
    *   **Cursor**: `["--model", config.model]`
    *   **Codex**: The current `codex` CLI wrapper might not support a simple `--model` flag. You need to verify if `codex exec` accepts a model flag or if it needs to be passed differently. If it's not supported, the doc should note that `model` is ignored for the `codex` backend or requires `extra_flags`.

### Final Verdict
**Ready to implement**, subject to the minor clarifications above. The schema is solid, the location (`.kd/config.json`) is correct, and the validation strategy is sound.
