---
from: claude
to: king
timestamp: 2026-02-14T03:22:16Z
---

This is clean. Every issue I raised in the last review has been addressed. A few final thoughts:

### What's Right

- **Two-distribution-concern framing** (lines 9-13) — this is the key insight and it's stated clearly up front. Skill ≠ package.
- **`skills/kingdom/`** not `kingdom/` — avoids collision with the Python package root, and makes the intent obvious when browsing the repo.
- **No `scripts/`** — correct. `kd doctor` already exists; wrapping it in a shell script is redundant indirection.
- **Delete root SKILL.md** — clean break. No ambiguity about which is authoritative.
- **Prerequisites as section 1** — an agent that can't run `kd` needs to know immediately, not after reading 400 lines of workflow.
- **Command inventory is complete** — audited against actual `--help`, all subcommands present.

### Minor Observations (Not Blockers)

**1. The `kd tk reopen` command is missing from the inventory (line 112).** It exists per `kd tk --help`. Low importance — it's a rarely-used command — but the design says "complete command inventory," so it should be complete.

**2. On the open question about `kd install-skill`** — I'd recommend yes, bundle it. The friction point with skills is always installation. If `uv tool install kingdom` gives you `kd` and then `kd install-skill` copies the skill directory to `~/.claude/skills/kingdom`, that's a one-command setup. The skill files are just markdown — they add negligible size to the package. You'd include `skills/` in the package data via `pyproject.toml` and have the command copy from the installed package location. This also solves version drift: the skill always matches the CLI version.

**3. On the references split question** — I'd keep the three-file split for now and collapse during implementation if any file ends up under ~40 lines. Council patterns will be substantial (the "don't synthesize" philosophy, async vs sync, `--to` for targeted queries, thread watching). Tickets will be substantial (lifecycle states, dependencies, backlog management). Peasants might be thin — if it's just "run `kd peasant start <id>`, optionally `--hand` for serial mode," it could fold into SKILL.md.

**4. On CI validation** — yes, add it to pre-commit if `skills-ref validate` is available. It's a fast check and prevents spec drift. But don't block on this for the initial implementation.

### Verdict

This is ready to implement. The architecture is correct per spec, the decisions are sound, the migration path is clear. No remaining issues that would change the structure or approach. Go build it.
