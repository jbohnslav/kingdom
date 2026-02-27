---
id: "fe6c"
status: open
deps: [5afc, ffc8, bb0e]
links: []
created: 2026-02-27T11:55:39Z
type: task
priority: 3
---
# Bring docs in sync (R9)

## Problem

Documentation has drifted from reality. Design docs reference commands that never shipped or were removed, and the README only covers ~10 of 40+ real commands.

## Acceptance Criteria

- [ ] `multi-agent-redesign.md` and `council-design.md` marked with historical banner: `> **Historical** — this document describes an earlier design. See README for current commands.`
- [ ] `cli-skill-architecture.md` updated: remove references to `council critique`, `council doctor`, `--open` flag; add real command surface
- [ ] README updated with CLI reference section or link to `kd --help` output; covers peasant lifecycle, ticket dependencies, council watch/retry
- [ ] Kingdom skill (`skills/kingdom/SKILL.md`) updated to reflect actual commands after surface redesign
- [ ] `AGENTS.md` updated to reflect new command surface (especially `council chat` replacing top-level `chat`)
