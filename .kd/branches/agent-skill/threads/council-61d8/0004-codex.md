---
from: codex
to: king
timestamp: 2026-02-14T03:02:29Z
---

I’ll read the three sources you named (`.kd/branches/agent-skill/design.md`, root `SKILL.md`, and `third-party/skills` spec files), then give a correctness review against spec with concrete gaps and recommended changes.
I verified the live spec details from `agentskills.io` to avoid stale assumptions. Next I’m cross-checking the design’s proposed frontmatter/command examples against actual `kd` CLI behavior so the review is concrete.
Assessment: **mostly sound direction**, but there are a few spec/portability gaps and a couple of overclaims.

1. **Medium: “gating via metadata requires-bins” is not a spec-level guarantee.**
`metadata` is just arbitrary key/value and not standardized for enforcement; core spec does not define `requires-bins` behavior.
Refs: `.kd/branches/agent-skill/design.md:25`, `.kd/branches/agent-skill/design.md:69`, `.kd/branches/agent-skill/design.md:71`
Spec basis: metadata is extension data, not required behavior (`agentskills.io/specification`).

2. **Medium: platform support claim is stronger than the design scope supports.**
Design says cross-platform support, but explicitly excludes platform adapters. Without adapters, “works on Cursor/Codex” is conditional, not guaranteed.
Refs: `.kd/branches/agent-skill/design.md:23`, `.kd/branches/agent-skill/design.md:32`, `.kd/branches/agent-skill/design.md:95`

3. **Medium: command/path truth in current root skill is stale, and design should explicitly treat it as migration debt.**
Current `SKILL.md` has outdated council storage, outdated peasant commands, and outdated install instructions.
Refs: `SKILL.md:47`, `SKILL.md:82`, `SKILL.md:99`, `SKILL.md:135`
CLI reality refs: `src/kingdom/thread.py:6`, `src/kingdom/cli.py:1118`, `src/kingdom/cli.py:2064`

4. **Low: frontmatter sample is close, but should be stricter to avoid validator/client issues.**
`name` rules are stricter than “just lowercase/hyphens”; also avoid relying on nonstandard keys semantics.
Refs: `.kd/branches/agent-skill/design.md:59`, `.kd/branches/agent-skill/design.md:68`, `.kd/branches/agent-skill/design.md:69`
Spec basis: name must match parent dir + no consecutive hyphens; metadata is string->string (`agentskills.io/specification`).

5. **Low: structure choice is valid, but discoverability may be better under `skills/kingdom/`.**
`kingdom/` at repo root is spec-valid, but many tools/conventions scan skill directories like `skills/*` or tool-specific dirs.
Refs: `.kd/branches/agent-skill/design.md:37`, `.kd/branches/agent-skill/design.md:47`

What I would change:
1. Keep proposed structure, but use `skills/kingdom/` (or clearly document why not).
2. In frontmatter, keep only portable fields with conservative semantics: `name`, `description`, optional `compatibility`, optional simple `metadata` (no implied enforcement).
3. Reword platform section to “portable core skill; platform wiring required per tool.”
4. Add a concrete validation/testing section in the design now: `skills-ref validate`, plus smoke tests for at least one host and one command (`kd status`).
5. Add explicit migration step: deprecate/replace root `SKILL.md` so scanners don’t pick stale instructions.

No files were modified.
