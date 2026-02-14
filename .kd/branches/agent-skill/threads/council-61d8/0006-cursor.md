---
from: cursor
to: king
timestamp: 2026-02-14T03:22:02Z
---

The updated design document is **excellent and ready for implementation**.

### Final Review

1.  **Structure (`skills/kingdom/`):**
    *   **Correct:** This is the standard layout for a standalone skill. It clearly separates the *instructional* component (the skill) from the *functional* component (the Python package).
    *   **Zero Code:** Removing `scripts/` simplifies the skill immensely. Relying on `kd doctor` for diagnostics is the right architectural choice—keep logic in the CLI, instructions in the skill.

2.  **Frontmatter:**
    *   **Correct:** The YAML frontmatter is spec-compliant.
    *   **Compatibility:** Explicitly stating `compatibility: Requires Python 3.10+, kd CLI` is good practice.

3.  **Workflow:**
    *   **Sound:** The decision to keep `kd` commands as bash invocations (rather than wrapping them) remains the strongest part of this design. It ensures the agent learns the actual tool, not a fragile abstraction layer.

4.  **Open Question (PyPI bundling):**
    *   **Recommendation:** *Yes*, eventually. Including the skill files in the PyPI package and adding a `kd install-skill` command would be a fantastic UX improvement. It would allow a user to run `uv tool install kingdom && kd install-skill` to fully bootstrap their agent environment. However, this can be a future enhancement. For now, the manual copy/symlink instructions are sufficient and standard.

### Implementation Plan

You are good to proceed. I will now execute the changes as described in the "Migration" section of the design doc:

1.  Create `skills/kingdom/` and `skills/kingdom/references/`.
2.  Write `skills/kingdom/SKILL.md` with the new frontmatter and core workflow.
3.  Write the reference files (`council.md`, `tickets.md`, `peasants.md`) by extracting and refining content from the old `SKILL.md`.
4.  Delete the root `SKILL.md`.

I will start by creating the directory structure.
