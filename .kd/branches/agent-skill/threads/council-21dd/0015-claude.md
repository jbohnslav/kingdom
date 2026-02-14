---
from: claude
to: king
timestamp: 2026-02-14T02:41:12Z
---

Now I have a complete picture. Let me compile the analysis.

---

## Complete Analysis: Agent Skills Spec + Kingdom as a Skill

### 1. The Agent Skills Specification

The spec is maintained at [agentskills.io/specification](https://agentskills.io/specification). It's an open standard published by Anthropic and adopted by Microsoft, OpenAI, Cursor, GitHub, Atlassian, Figma, and others. Here's the core:

**Minimum viable skill:**
```
skill-name/
└── SKILL.md    # YAML frontmatter + markdown body
```

**Required frontmatter fields:**

| Field | Constraints |
|---|---|
| `name` | 1-64 chars, lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens, must match parent directory name |
| `description` | 1-1024 chars, describes what + when to use |

**Optional fields:** `license`, `compatibility` (max 500 chars, environment requirements), `metadata` (arbitrary key-value), `allowed-tools` (space-delimited, experimental).

**Optional directories:** `scripts/` (executable code), `references/` (docs loaded on demand), `assets/` (templates, static resources).

**Progressive disclosure (3 levels):**
1. Metadata (~100 tokens) — loaded at startup for all skills
2. SKILL.md body (<5000 tokens recommended, <500 lines) — loaded when skill activates
3. Resources (unlimited) — loaded as needed

**Claude Code extensions** beyond the open spec: `disable-model-invocation`, `user-invocable`, `context: fork`, `agent`, `mode`, `argument-hint`, hooks. These are Claude Code-specific and not portable.

### 2. Best Practices from Top Skills

From the official `skill-creator` skill and `obra/superpowers` (the most influential community collection):

- **Description is everything** — it's the *only* thing loaded at startup. Include both what it does and when to use it. All "when to use" logic goes here, not in the body.
- **Concise is key** — the context window is shared. Challenge every paragraph: "Does this justify its token cost?"
- **Degrees of freedom** — narrow bridge = specific scripts; open field = text instructions.
- **One level deep** — SKILL.md references files directly, never nested chains.
- **Imperative form** — "Extract text from PDF" not "This skill extracts text from PDFs."
- **No extraneous files** — no README, CHANGELOG, INSTALLATION_GUIDE. Just SKILL.md + resources.
- **Scripts for determinism** — repeated code should be a script in `scripts/`, not regenerated each time.

### 3. How Kingdom Maps to the Skill Model

Your existing `SKILL.md` at the repo root is a good start but has issues against the spec:

**Problems with current SKILL.md:**
- It's a flat file, not in a `kingdom/` directory (spec requires name matches parent dir)
- Missing proper frontmatter (`name`, `description` fields)
- The "Installation" section at the bottom references a nonexistent `~/.claude/skills.yaml`
- It's ~137 lines — well within the 500-line limit, that's fine
- Council response paths reference `logs/council/<run-id>/` which doesn't match the actual `.kd/branches/<branch>/threads/` structure

**The architectural insight from your own design doc is correct:** Kingdom is *both* a CLI toolkit *and* a skill. The skill teaches agents the workflow; the CLI executes it. These are complementary.

### 4. What a Proper Kingdom Skill Package Would Look Like

```
kingdom/                          # skill directory (name = "kingdom")
├── SKILL.md                      # Core workflow instructions
├── references/
│   ├── council.md                # Deep dive on council usage patterns
│   ├── tickets.md                # Ticket lifecycle, commands, statuses
│   └── peasants.md               # Peasant/worktree workflow details
└── scripts/
    └── check-kd.sh               # Preflight: verify kd is installed + on PATH
```

**Frontmatter would be:**
```yaml
---
name: kingdom
description: >
  Multi-agent design and development workflow using the kd CLI.
  Manages design→breakdown→tickets→development lifecycle with
  council consultation (multi-model perspectives) and peasant
  workers. Use when the user mentions kd, kingdom, council,
  design docs, ticket breakdown, or multi-agent workflow.
  Requires the kd CLI to be installed and on PATH.
compatibility: Requires kd CLI (pip install kingdom), git
---
```

### 5. Which kd Commands Make Sense as Skills vs. Staying as Bash

The ticket asks this directly. My recommendation:

**Should be the skill (SKILL.md instructions):**
- When to consult council vs. just do the work
- How to iterate on design.md
- How to structure breakdown.md
- Workflow phase transitions (design → breakdown → tickets → dev)
- How to read council responses (don't synthesize, let King decide)

**Should stay as bash commands (referenced from skill):**
- `kd start`, `kd status`, `kd done` — lifecycle
- `kd council ask "..."` — multi-model orchestration
- `kd tk list/show/start/close` — ticket management
- `kd peasant start <id>` — worker spawning
- `kd design`, `kd design show` — design document management

The skill teaches *when and why*; the CLI handles *how*. An agent reading the skill learns the workflow, then executes `kd` commands via bash.

### 6. Cross-Platform Portability

The ticket specifically says "agent-platform-agnostic, not tied to Claude Code's specific skill format." The open spec achieves this — it's just a directory with SKILL.md. But:

- **Claude Code**: Full native support. Skills in `.claude/skills/kingdom/SKILL.md` or `~/.claude/skills/kingdom/SKILL.md`.
- **Cursor**: Supports the spec experimentally. The skill would work.
- **Codex**: No native skill loader, but the SKILL.md can be referenced via system prompt or CLAUDE.md equivalent.
- **Other agents**: Any agent that reads markdown instructions can consume a SKILL.md. The format is just YAML + markdown.

The safe approach: keep the skill to the open spec fields only (name, description, license, compatibility, metadata). Don't use Claude Code extensions (`disable-model-invocation`, `context: fork`, etc.) in the portable version. Those can go in a Claude Code-specific wrapper if needed.

### 7. Security Considerations

Snyk's ToxicSkills research found **36.8% of public skills** on ClawHub contain security issues, including 341 confirmed malicious skills. Kingdom's skill is safe because:
- It's first-party (you wrote it)
- It only teaches workflow, it doesn't inject code
- The `scripts/` directory would only contain a preflight check

But if Kingdom is ever published to a registry, the `allowed-tools` field should be used to restrict what the skill can do (e.g., `Bash(kd:*) Read Grep Glob`).

### 8. What's Missing to Close Ticket cf85

Per the acceptance criteria:

- [x] Open source agent skills spec reviewed and documented — covered above
- [x] Understand which agent platforms support it — Claude Code (native), Cursor (experimental), Codex (manual), others (markdown-compatible)
- [ ] At least one kd command registered and working as a skill — the existing SKILL.md needs restructuring into a proper `kingdom/SKILL.md` directory with correct frontmatter
- [ ] Document which kd commands make sense as skills vs staying as bash — covered in section 5 above
- [ ] Notes on any limitations or gotchas — covered (no auto-invoke for destructive ops, progressive disclosure budget, cross-platform extension fields)

The main work remaining is restructuring the SKILL.md into a proper skill directory and testing that it actually loads and works in Claude Code (and ideally Cursor).
