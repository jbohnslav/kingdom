# Design: agent-skill

## Goal

Package Kingdom as a spec-compliant Agent Skill that can be installed in any repo to teach agents the kd workflow — completely separate from the Python package that provides the `kd` CLI.

## Context

Kingdom has two distribution concerns:

1. **The Python package** — published on PyPI, installed with `uv tool install kingdom`, provides the `kd` CLI binary
2. **The agent skill** — a standalone directory with instructions that teach agents how to use `kd`

These are separate things. The skill contains zero code — just markdown instructions and references. This matches the pattern used by existing skills (docx, pptx, pdf, slack-gif-creator) which all require external tool installation (`npm install -g`, `pip install`, `apt-get install`) and bundle only instructions + helper scripts.

The current `SKILL.md` at the repo root conflates these two concerns and is not spec-compliant:

- Missing YAML frontmatter (`name`, `description`)
- References nonexistent paths (`logs/council/<run-id>/` instead of `.kd/branches/<branch>/threads/`)
- Stale command signatures (`kd council last`, `kd peasant <id>` instead of `kd peasant start <id>`)
- Installation section references nonexistent `~/.claude/skills.yaml`
- No progressive disclosure (no `references/` directory)

The [Agent Skills spec](https://agentskills.io/specification) is an open standard adopted by Anthropic, Microsoft/GitHub, OpenAI, Cursor, Atlassian, and others. A skill is a directory with a `SKILL.md` file containing YAML frontmatter + markdown instructions, plus optional `scripts/`, `references/`, and `assets/` directories.

## Requirements

- Spec-compliant skill directory with valid frontmatter (name, description, compatibility)
- Correct progressive disclosure: metadata (~100 tokens) → instructions (<5000 tokens, <500 lines) → references (on demand)
- Skill is purely instructional — no Python source, no package code, no scripts
- Accurately documents the kd workflow with correct command signatures (audited against `--help`)
- Portable core; no Claude Code-specific extensions (`user-invocable`, `context`, `allowed-tools`)
- Tells agents how to install `kd` if missing (`uv tool install kingdom`)

## Non-Goals

- Publishing to ClawHub or any registry (for now)
- Platform-specific adapters (Codex agents.yaml, Cursor .cursor/rules)
- Slash command registration (agents invoke kd via bash, the skill teaches when/why)
- Multi-way council deliberation mode (separate ticket 520a)
- Bundling kd source code inside the skill

## Decisions

- **Skill lives at `skills/kingdom/`** inside the repo: a clean standalone directory containing only skill files (SKILL.md + references/). No Python source, no pyproject.toml, no tests. This matches every example skill in the spec repo — skills are self-contained instruction directories. Users install by copying or symlinking this directory into their agent's skill discovery path.
- **Skill is separate from the package**: the skill teaches agents the workflow; the `kd` CLI is installed separately via `uv tool install kingdom` (or `pip install kingdom`). The `compatibility` field and a Prerequisites section in the body tell agents how to install the tool.
- **Skill teaches workflow, CLI stays as bash**: SKILL.md instructs agents on *when* and *why* to use kd commands. The actual `kd` invocations are bash commands, not skill-wrapped abstractions.
- **Progressive disclosure via `references/`**: keep SKILL.md under 500 lines with core workflow. Move detailed council patterns, ticket lifecycle, and peasant docs into `references/`.
- **No `scripts/` directory**: `kd` is the interface, `kd doctor` handles preflight. No wrapper scripts needed.
- **Delete root `SKILL.md`**: the current root SKILL.md is a non-compliant prototype. Replace it with the new `skills/kingdom/` directory. Optionally leave a one-line note in CLAUDE.md pointing to the skill location.
- **Portable core only**: no Claude Code extensions. These can be added later in a platform-specific overlay if needed.

## Proposed Structure

```
skills/kingdom/                   # standalone skill directory (name = "kingdom")
├── SKILL.md                      # Core workflow + frontmatter (<500 lines)
└── references/
    ├── council.md                # Council usage patterns, when to consult
    ├── tickets.md                # Ticket lifecycle, commands, statuses
    └── peasants.md               # Peasant/worktree workflow details
```

Installed into a repo or agent environment by copying/symlinking:
```bash
# Claude Code
cp -r skills/kingdom ~/.claude/skills/kingdom

# Or symlink from a clone
ln -s /path/to/kingdom/skills/kingdom ~/.claude/skills/kingdom

# The kd CLI itself is installed separately
uv tool install kingdom
```

## Frontmatter

```yaml
---
name: kingdom
description: >
  Multi-agent design and development workflow using the kd CLI.
  Manages design, breakdown, tickets, council consultation (multi-model
  perspectives), and peasant workers. Use when starting a new feature
  branch, breaking down work into tickets, consulting multiple AI models
  for design decisions, or managing development workflow with kd commands.
  Requires the kd CLI to be installed and on PATH.
compatibility: Requires Python 3.10+, kd CLI (uv tool install kingdom), git
---
```

## SKILL.md Body Outline

1. **Prerequisites** — `uv tool install kingdom` (or `pip install kingdom`), verify with `kd --help`, then `kd doctor` for agent CLI readiness
2. **Core workflow** — the linear path: start → design → council → breakdown → tickets → work → done
3. **Command reference** — concise table of all kd commands with correct signatures
4. **Council philosophy** — don't synthesize responses, let King read directly; when to consult vs. just do the work
5. **References** — pointers to `references/*.md` for deep dives

One sentence of role framing ("You assist the King using the kd CLI") is enough — no full role-play section.

## Core Command Inventory

All commands stay as bash. The skill teaches workflow; kd is the interface:

- `kd init` — initialize .kd/ directory
- `kd start/status/done` — branch lifecycle
- `kd doctor` — check agent CLIs are installed
- `kd design/design show/design approve` — design docs
- `kd breakdown/breakdown --apply` — ticket breakdown
- `kd council ask/show/list/watch/reset` — council queries
- `kd tk create/list/show/start/close/reopen` — ticket CRUD
- `kd tk move/edit/ready/pull` — ticket organization
- `kd tk dep/undep` — dependency management
- `kd tk assign/unassign` — agent assignment
- `kd peasant start <id>` — worker spawning (worktree)
- `kd work` — run autonomous agent loop on a ticket

## Platform Support

Portable core skill; platform-specific wiring required per tool:

| Platform | How |
|----------|-----|
| Claude Code | Copy/symlink `skills/kingdom/` into `~/.claude/skills/` |
| Cursor | Experimental skill spec support, or reference SKILL.md via .cursor/rules |
| Codex | Reference SKILL.md content in system prompt or agents.yaml |
| Others | Any agent that reads markdown instructions can consume SKILL.md |

## Migration

1. **Create `skills/kingdom/`** directory with spec-compliant SKILL.md
2. **Create `skills/kingdom/references/`** with council, tickets, and peasants docs
3. **Delete root `SKILL.md`** — replaced by the new skill directory
4. **Update CLAUDE.md** if needed to point to the new skill location
5. **Validate** with `skills-ref validate skills/kingdom/` if available
6. **Smoke test**: install as skill in Claude Code, verify an agent can follow the workflow

## Open Questions

- Should we validate the skill with `skills-ref validate` as part of CI/pre-commit?
- How much of the current SKILL.md content belongs in the body vs. references? (Target: body <5000 tokens, <500 lines)
- Should `references/` be three files (council, tickets, peasants) or a single `commands.md`? Depends on whether each justifies its own file length-wise.
- Should the PyPI package include the skill directory so `uv tool install kingdom` also provides the skill files? (e.g. `kd install-skill` command that copies the skill to the right place)
