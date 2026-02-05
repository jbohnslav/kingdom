# Design: cleanup

## Goal

Simplify Kingdom to a branch-centric CLI that assists coding agents. Remove legacy tmux/REPL patterns, integrate ticket management directly, and align the folder structure with git branches.

## Context

Kingdom evolved from a tmux-based "all-in-one text interface" to a CLI that assists existing coding agents. The key insight: **git branches are already how developers organize work**. Kingdom should align with that, not create a parallel "run" abstraction.

Current problems:
- `src/kingdom/tmux.py` - 121 lines of unused tmux orchestration
- `src/kingdom/hand.py` - 450 line Python REPL that duplicates what coding agents do
- `.kd/runs/<name>/` abstraction is redundant with git branches
- Tickets in separate `.tickets/` directory (managed by external `tk` CLI)
- `.kd/current` tracked in git but deleted by `kd done` (dirty state)
- Many outdated docs (MVP.md, dispatch-design.md, etc.)

## New Architecture

### Branch = Organizing Principle

```
.kd/
├── branches/                  # all branch work lives here
│   ├── feature-oauth-refresh/ # normalized from "feature/oauth-refresh"
│   │   ├── design.md          # tracked
│   │   ├── breakdown.md       # tracked
│   │   ├── learnings.md       # tracked
│   │   ├── tickets/           # tracked
│   │   │   ├── kin-a1b2.md
│   │   │   └── kin-c3d4.md
│   │   └── state.json         # ignored (operational)
│   └── fix-login-bug/         # normalized from "fix-login-bug"
│       └── ...
├── backlog/                   # special: tickets not yet assigned to a branch
│   └── tickets/
│       └── kin-xyz.md
├── archive/                   # completed branches move here
│   └── feature-oauth-refresh/
├── worktrees/                 # ignored - ephemeral peasant workspaces
│   └── kin-a1b2/
├── current                    # ignored - pointer to active branch folder
└── config.json                # tracked (if shared settings)
```

Clear separation: `branches/` for active work, `backlog/` for unassigned tickets, `archive/` for completed work.

### Branch Name Normalization

Git branch → directory name:
- `feature/oauth-refresh` → `feature-oauth-refresh`
- `jrb/fix-bug` → `jrb-fix-bug`
- Slashes → dashes
- ASCII only, lowercase
- Stored in `state.json`: `{"branch": "feature/oauth-refresh"}`

### Integrated Ticket Management

Merge `tk` functionality directly into `kd` as typer subcommands:

```bash
kd ticket create "Add OAuth refresh"     # creates in current branch's tickets/
kd ticket create "Future idea" --backlog # creates in backlog/tickets/
kd ticket list                           # list tickets for current branch
kd ticket list --all                     # list all tickets across branches
kd ticket start kin-a1b2                 # set status to in_progress
kd ticket close kin-a1b2                 # set status to closed
kd ticket move kin-a1b2 feature-dark-mode # move ticket to another branch
kd ticket show kin-a1b2                  # display ticket
kd ticket dep kin-a1b2 kin-c3d4          # add dependency
kd ticket ready                          # list tickets ready to work on
```

Ticket format (YAML frontmatter + markdown, same as current tk):
```yaml
---
id: kin-a1b2
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
---
# Ticket title

Description here.

## Acceptance Criteria
- [ ] Criterion 1
```

## Requirements

### 1. Delete legacy code
- Delete `src/kingdom/tmux.py`
- Delete `src/kingdom/hand.py`
- Delete `tests/test_tmux.py`
- Remove all tmux imports from `cli.py`

### 2. Restructure CLI commands

**Remove:**
- `kd chat` (user talks to coding agent directly)
- `kd attach` (tmux-specific)

**Simplify:**
- `kd start <branch>` → create `.kd/<normalized-branch>/`, set current, optionally create git branch
- `kd done` → move current branch folder to archive/
- `kd status` → show current branch, tickets, design state

**Add:**
- `kd ticket` subcommand group (integrated tk)
- `kd archive <branch>` → explicit archive command

**Keep:**
- `kd council ask` (core value)
- `kd design` / `kd breakdown` (workflow helpers)
- `kd doctor` (CLI checks)

### 3. Migrate from runs/ to branch-based structure
- Rename `.kd/runs/` concept to branch-based folders
- Update `state.py` with branch name normalization
- Update gitignore patterns

### 4. Archive old documentation
Move to `docs/archive/`:
- `docs/MVP.md`
- `docs/MVP-breakdown.md`
- `docs/mvp-next-step-design.md`
- `docs/dispatch-design.md`
- `docs/dispatch-cli-design-v2.md`
- `docs/design_breakdown_polish.md`
- `docs/designing_logs.md`
- `docs/tech-stack.md`

### 5. Update README
- Explain branch-centric workflow
- Document `kd ticket` commands
- Remove third-party tk reference

### 6. Migrate existing .tickets/
- Move existing tickets to `backlog/tickets/` or appropriate branch folders
- Delete `.tickets/` directory after migration

## Non-Goals

- **New council features** - Subprocess architecture stays the same
- **Peasant automation** - Keep simple (create worktree, print instructions)
- **Multi-repo support** - One repo at a time

## Gitignore Strategy

`.kd/.gitignore`:
```
# Operational state (not tracked)
*.json
*.jsonl
*.log
*.session
**/logs/
**/sessions/
worktrees/
current
```

Tracked: design.md, breakdown.md, learnings.md, tickets/*.md

## Decisions (after council consultation)

1. **Branch-centric architecture** - Eliminate "run" abstraction. Use normalized git branch names under `.kd/branches/`. Branch `feature/oauth-refresh` → `.kd/branches/feature-oauth-refresh/`. Clear separation from special folders (backlog, archive, worktrees).

2. **Delete hand.py entirely** - No REPL. User talks to coding agent directly. kd CLI is for agents to call, not humans to chat with.

3. **Delete tmux.py entirely** - No terminal management. Kingdom is a CLI toolkit, not a terminal application.

4. **Integrate tk into kd** - Rewrite ticket management as `kd ticket` subcommands using typer. Same file format (YAML frontmatter + markdown). Tickets live in branch folders.

5. **Backlog as special folder** - `.kd/backlog/tickets/` holds tickets not yet assigned to a branch.

6. **Archive for completed work** - When branch merges, `kd done` or `kd archive` moves folder to `.kd/archive/`.

7. **Hybrid git tracking** - Track markdown (design, breakdown, learnings, tickets). Ignore operational state (json, logs, sessions, worktrees, current).

## Implementation Order

### Phase 1: Delete legacy code
1. Delete `src/kingdom/tmux.py`
2. Delete `src/kingdom/hand.py`
3. Delete `tests/test_tmux.py`
4. Remove tmux/hand imports from `cli.py`
5. Remove `kd chat`, `kd attach` commands

### Phase 2: Restructure to branch-based
6. Add branch name normalization to `state.py`
7. Rename "runs" concept to branch-based folders
8. Update `kd start` to use normalized branch names
9. Update `kd done` to archive to `.kd/archive/`
10. Update `kd status` for new structure

### Phase 3: Integrate ticket management
11. Create `src/kingdom/ticket.py` with ticket CRUD
12. Add `kd ticket` subcommand group to CLI
13. Migrate existing `.tickets/` to backlog or branch folders
14. Remove references to external `tk` tool

### Phase 4: Documentation cleanup
15. Archive old docs to `docs/archive/`
16. Update README with new architecture
17. Update cli-skill-architecture.md if needed

## Files to Delete

- `src/kingdom/tmux.py`
- `src/kingdom/hand.py`
- `tests/test_tmux.py`

## Files to Archive (move to docs/archive/)

- `docs/MVP.md`
- `docs/MVP-breakdown.md`
- `docs/mvp-next-step-design.md`
- `docs/dispatch-design.md`
- `docs/dispatch-cli-design-v2.md`
- `docs/design_breakdown_polish.md`
- `docs/designing_logs.md`
- `docs/tech-stack.md`

## Open Questions (all resolved)

~~1. Runs: tracked or ignored?~~ → Hybrid: markdown tracked, json/logs ignored

~~2. What replaces kd chat?~~ → Nothing - user talks to coding agent directly

~~3. Rename run to feature?~~ → Eliminated entirely - use branch names

~~4. Ticket integration depth?~~ → Fully integrated into kd

~~5. hand.py role?~~ → Deleted entirely
