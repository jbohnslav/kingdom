---
from: cursor
to: king
timestamp: 2026-02-14T02:32:15Z
---

Based on my research of the `third-party/skills` and `third-party/openclaw` submodules, here is the information you requested regarding the Agent Skills specification and how to adapt Kingdom.

### 1. The Agent Skill Specification

The "Agent Skills" standard (compatible with OpenClaw and Claude) is a lightweight format for teaching agents new capabilities.

*   **Structure:** A skill is simply a **directory** containing a `SKILL.md` file.
*   **Format:** The `SKILL.md` file uses YAML frontmatter for metadata and Markdown for instructions.
*   **Required Frontmatter:**
    *   `name`: Unique identifier (kebab-case, e.g., `kingdom-cli`).
    *   `description`: Clear summary of what the skill does and when to use it.
*   **Optional Metadata (OpenClaw/ClawHub extensions):**
    *   `metadata`: A single-line JSON object for gating and installation.
        *   `requires.bins`: List of binaries that must exist (e.g., `["kd"]`).
        *   `requires.env`: Required environment variables.
        *   `install`: Instructions for installing dependencies (brew, npm, etc.).
    *   `user-invocable`: `true` (default) exposes it as a slash command to the user.

**Example `SKILL.md`:**
```markdown
---
name: kingdom
description: Manage software development lifecycle using the Kingdom CLI (design, tickets, council).
metadata: {"openclaw": {"requires": {"bins": ["kd"]}}}
---

# Kingdom CLI

You are the "Hand" assisting the King. Use the `kd` command to manage the project...

## Examples
- `kd council ask "Should we use Redis?"`
- `kd ticket list`
```

### 2. Best Practices from Popular Skills

*   **Gating is critical:** Use the `metadata` field to check for required binaries (`kd`). This prevents the agent from hallucinating success or failing confusingly if the tool isn't installed.
*   **Security First:** The documentation explicitly warns that skills are **untrusted code**. Malicious skills on ClawHub could exfiltrate secrets or run dangerous commands. Always audit `SKILL.md` and any included scripts before installing.
*   **Clear Context:** The Markdown body should define the agent's *persona* (e.g., "You are the Hand") and specific *workflows* (e.g., "When the King asks X, run Y").
*   **Slash Commands:** Exposing skills as slash commands (e.g., `/kingdom status`) is a popular pattern for user-driven workflows, though agents can also invoke them naturally via CLI.

### 3. Turning Kingdom into a "Proper" Agent Skill

We are very close. The `SKILL.md` currently in the root of the repo is already 90% of the way there. To make it a portable, installable skill:

1.  **Directory Structure:** Move `SKILL.md` into a dedicated folder, e.g., `skills/kingdom/SKILL.md`. This allows it to be installed via ClawHub or symlinked into `~/.openclaw/skills`.
2.  **Add Metadata:** Update the frontmatter to strictly declare the dependency on the `kd` binary. This ensures the skill only loads if Kingdom is actually installed.
3.  **Installation Helper:** Add an `install` block to the metadata so users (or agents) can auto-install Kingdom if it's missing (e.g., pointing to the pip install command or repo).

**Recommendation:**
I recommend we move the current `SKILL.md` to `.kd/skills/kingdom/SKILL.md` and update it with the strict metadata. This allows us to "install" it into any agent environment simply by pointing the agent to that directory or symlinking it.

Would you like me to proceed with creating this directory structure and updating the `SKILL.md` to match the official spec?
