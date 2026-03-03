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

## Implementation Plan

Run `kd --help`, `kd council --help`, `kd tk --help`, `kd tk deps --help`, and `kd peasant --help` first to get the authoritative command surface. Use that as the source of truth for all doc edits.

### Phase 1: Historical banners (trivial)

Add the historical banner to design docs. Don't rewrite their bodies.

- `docs/multi-agent-redesign.md`: Replace "Status: Proposed" with `> **Historical** — this document describes an earlier design. See README for current commands.`
- `docs/council-design.md`: Replace "Status: Implemented" with the same banner.
- `docs/cli-skill-architecture.md`: Add the same banner. Strip references to dead commands (`council critique`, `council doctor`, `--open` flag) but don't rewrite the whole file — it's 35KB of historical context.

### Phase 2: Fix README

Fix ghost commands and add missing workflow coverage. Don't add a full CLI reference — keep it as a curated overview.

- `kd init` → `kd start` (init doesn't exist)
- `kd chat --new` → `kd council chat --new`
- `kd breakdown` → remove or clarify it's a design-phase step done through the skill
- `kd design` → be specific: `kd design show` / `kd design approve`
- Add peasant review cycle (`kd peasant review`, `kd peasant accept`, `kd peasant reject`) to the workflow section — README currently shows start but not the review cycle
- Add a brief "Commands" section listing the top-level groups with one-line descriptions, pointing to `kd <command> --help` for details
- Mention `kd council chat` replacing top-level `kd chat`

### Phase 3: Fix SKILL.md + references

Editorial fixes, NOT regeneration from `--help`. The skill's workflow guidance and decision context is valuable — keep it.

- SKILL.md quick-ref: Add `kd tk deps add/remove/tree/cycle`, `kd peasant accept/reject/review/msg/read`
- `references/tickets.md`: Fix `kd tk dep` → `kd tk deps add`, `kd tk undep` → `kd tk deps remove`, priority range 0-3, remove `kd tk ready` → `kd tk list --ready`
- `references/peasants.md`: Remove `kd work <id>`, add accept/reject/review section
- `references/council.md`: Minor cleanup if needed

### Phase 4: CLAUDE.md (which AGENTS.md symlinks to)

- Replace any remaining `kd chat` references with `kd council chat`
- Keep it workflow-oriented, not exhaustive
- Don't touch the symlink — AGENTS.md → CLAUDE.md is correct

### What NOT to do

- Don't auto-generate docs from `--help` output
- Don't merge AGENTS.md into README
- Don't rewrite `cli-skill-architecture.md` — banner it and remove dead command refs only
- Don't add a full command reference to README

## Acceptance Criteria

- [ ] `multi-agent-redesign.md` and `council-design.md` marked with historical banner
- [ ] `cli-skill-architecture.md` has historical banner + dead command references removed
- [ ] README ghost commands fixed (`init`, `chat`, `breakdown`, `design`)
- [ ] README covers peasant review cycle (review/accept/reject)
- [ ] README has brief "Commands" section listing top-level groups
- [ ] SKILL.md quick-ref updated with current commands
- [ ] SKILL.md reference files fixed (tickets, peasants, council)
- [ ] CLAUDE.md updated (`kd chat` → `kd council chat`)
- [ ] All command references verified against actual `--help` output
