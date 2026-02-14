---
from: codex
to: king
timestamp: 2026-02-14T02:42:09Z
---

I’ll first read ticket `cf85` and locate the local skills submodule context, then I’ll do a broad web sweep of official specs/docs plus popular public skill examples and synthesize a concrete “Kingdom as installable skill” plan.
I found both the ticket and a local `third-party/skills` spec submodule. Next I’m reading those first so the web research can be anchored to your exact target format and constraints.
I’ve got the local spec pointers and ticket context; now I’m doing the external research pass across official spec/docs (agentskills.io, Anthropic, platform docs, and ClawHub/OpenClaw security guidance), then I’ll map it back to a concrete Kingdom packaging strategy.
I found a direct official link from agentskills.io to “authoring best practices”; I’m opening that plus the reference SDK and example skills repo to ground the recommendations in the canonical guidance.
I’m now mining the local `third-party/skills` examples to extract concrete patterns from real, widely-used skills (structure, length, script usage, references), so recommendations aren’t theoretical.
I have enough official external sources for the spec and Anthropic behavior. I’m now pulling the OpenClaw/ClawHub docs (local submodule + upstream) to answer the malicious-skill risk and safe adoption guidance concretely.
Read and done:
- Ticket: `.kd/branches/agent-skill/tickets/cf85.md:1`
- Local skills submodule/spec/docs: `third-party/skills/*`, `third-party/openclaw/docs/tools/*`
- External research: AgentSkills spec + Anthropic + Codex + OpenClaw/ClawHub + Cursor docs

**1) What is the skill specification?**
- The open standard is **Agent Skills** (`agentskills.io`), not Claude-only format.
- A skill is a directory with required `SKILL.md` frontmatter (`name`, `description`) plus instructions body.
- Optional common structure is `scripts/`, `references/`, `assets/`, plus optional setup/install metadata.
- Discovery/loading is platform-defined, but the spec defines format + metadata model + invocation intent (natural-language triggering, not a universal slash-command schema).
- Namespaced metadata is allowed for platform extensions (so portable core + platform-specific extras is expected).

Important gap in Kingdom right now:
- `SKILL.md:1` is not spec-compliant (no YAML frontmatter), so it is not a portable AgentSkills skill yet.

**2) Best practices from popular skills**
Patterns that consistently show up in official/curated skills (Anthropic + OpenAI catalogs):
- High-signal `description` that encodes **when to trigger** and **when not to**.
- Workflow-first docs: decision trees/phases/checklists (`docx`, `mcp-builder`, `doc-coauthoring`).
- Progressive disclosure: short core instructions, move bulky detail to `references/`.
- Use scripts for brittle/repeatable steps; keep prose for judgment calls.
- Include concrete I/O examples and output templates.
- Bake in safety constraints: confirmations for risky actions, scope boundaries, read-only defaults unless explicitly asked.
- Add evaluation loops (quality checks, regression checks, “did this actually help?”).

**3) How to turn Kingdom into a proper installable skill (any repo)**
Use a **portable core + adapters** model.

Portable core (AgentSkills-compliant):
- `skills/kingdom/SKILL.md` with strict frontmatter:
  - `name: kingdom`
  - `description:` explicit triggers like “design breakdown tickets council peasant workflow with kd”
- `skills/kingdom/scripts/`:
  - thin wrappers for `kd status`, `kd council ask`, `kd peasant start`, etc.
  - wrappers should enforce guardrails (confirm before destructive actions).
- `skills/kingdom/references/`:
  - `workflow.md`, `council.md`, `ticketing.md`, `troubleshooting.md`
- Keep `SKILL.md` short; push details into references.

Platform adapters (because slash commands are not standardized in core spec):
- **Codex**: add `agents/openai.yaml` for command prefixes/routing to wrappers.
- **OpenClaw**: use `metadata.openclaw` (`user-invocable`, optional command dispatch).
- **Claude Code**: install as skill/plugin; trigger mainly via natural-language intent.
- **Cursor**: no clear AgentSkills-native path; use `.cursor/rules` + repo `AGENTS.md` fallback.

Practical recommendation for cf85 acceptance criteria:
- Do a first POC with one command path (`kd status`) exposed via skill + wrapper + one platform adapter.
- Then add `kd council ask` and `kd peasant start`.
- Document “skill-worthy vs raw bash”:
  - Skill-worthy: multi-step workflows, policy-heavy, high-context tasks.
  - Raw bash: one-off simple shell ops.

**Security note (ClawHub warning)**
- Treat third-party skills as untrusted code, pin versions, review `SKILL.md` + scripts before enabling, and prefer curated/internal allowlists for production teams.

Sources:
- https://agentskills.io/specification
- https://agentskills.io/integrate-skills
- https://agentskills.io/authoring-best-practices
- https://raw.githubusercontent.com/openai/skills/main/README.md
- https://raw.githubusercontent.com/openai/skills/main/references/authoring-skills/writing-effective-skill-descriptions.md
- https://raw.githubusercontent.com/openai/skills/main/references/authoring-skills/optimizing-skills-for-agents-openai-yaml.md
- https://developers.openai.com/codex/skills
- https://docs.claude.com/en/docs/agents-and-tools/skills/overview
- https://docs.claude.com/en/api/skills-guide
- https://cursor.com/docs/context/rules
- https://cursor.com/docs/context/mcp
- `SKILL.md:1`
- `.kd/branches/agent-skill/tickets/cf85.md:1`
- `third-party/skills/README.md:1`
- `third-party/skills/spec/agent-skills-spec.md:1`
- `third-party/openclaw/docs/tools/skills.md:9`
- `third-party/openclaw/docs/tools/clawhub.md:10`
