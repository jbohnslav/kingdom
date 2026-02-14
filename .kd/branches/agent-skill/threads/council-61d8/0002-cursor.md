---
from: cursor
to: king
timestamp: 2026-02-14T03:00:52Z
---

The design document is **sound and compliant** with the Agent Skills specification. The proposed structure and decisions align well with the best practices observed in the `third-party/skills` repository.

### Evaluation

1.  **Structure (`kingdom/SKILL.md`):**
    *   **Correct:** Moving the skill into a dedicated `kingdom/` directory at the repo root is strictly required by the spec (which defines a skill as a *folder* containing `SKILL.md`).
    *   **Correct:** Using `references/` for progressive disclosure is a best practice to keep the main context window light (<500 lines) while keeping detailed docs available.

2.  **Frontmatter:**
    *   **Correct:** The required `name` and `description` fields are present.
    *   **Suggestion:** The design proposes a flat YAML `metadata` block (`requires-bins: kd`). While compliant with the base spec, if you want **automatic gating** (where the agent runtime hides the skill if `kd` is missing), you should prefer the OpenClaw-style JSON single-line format:
        ```yaml
        metadata: {"openclaw": {"requires": {"bins": ["kd"]}}}
        ```
        This is not strictly required for the skill to *work* (the LLM can read the text requirements), but it enables platform-native features like "grey out this skill if kd isn't installed."

3.  **Workflow (Bash vs. Wrappers):**
    *   **Sound:** The decision to **not** wrap `kd` commands in scripts is excellent. `kd` is already a CLI designed for humans/agents. The skill should act as the "manual" for the CLI, not a wrapper library. This reduces maintenance and lets the agent use `--help` naturally.

4.  **Installation:**
    *   **Correct:** The design fixes the broken installation instructions in the current `SKILL.md`. Symlinking the `kingdom/` directory is the standard way to "install" a local skill.

### Recommendation

**Proceed with the design as written.**

The only optional tweak is to update the `metadata` field in the frontmatter to the JSON format if you want explicit binary gating support in OpenClaw/ClawHub-compatible runners. Otherwise, the proposed YAML is perfectly readable by the model.

**Next Step:**
I can now implement this by:
1.  Creating the `kingdom/` directory.
2.  Moving and rewriting `SKILL.md` to `kingdom/SKILL.md` with the new frontmatter and structure.
3.  Creating the `kingdom/references/` directory and extracting the detailed sections (Council, Tickets, Peasants) into separate files.
4.  Creating the `kingdom/scripts/check-kd.sh` script.
