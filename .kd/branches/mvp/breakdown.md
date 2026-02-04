# Breakdown: cleanup

## Phase 1: Delete Legacy Code

### T0: Fix .kd/current gitignore
**Priority:** 0 (highest - quick win)
**Dependencies:** none

Fix the dirty git state caused by `.kd/current`:
- Add `current` to `.kd/.gitignore`
- Remove `current` from git tracking if present (`git rm --cached`)
- Commit the gitignore fix

**Acceptance Criteria:**
- [ ] `.kd/.gitignore` contains `current`
- [ ] `git status` is clean after `kd done` deletes current
- [ ] Committed to repo

---

### T1: Remove tmux/hand from CLI
**Priority:** 0
**Dependencies:** T0

Remove all references to legacy modules from CLI before deleting them:
- Remove all tmux imports from `cli.py`
- Remove all hand imports from `cli.py`
- Remove `kd chat` command
- Remove `kd attach` command
- Remove `hand_command()` function
- Clean up any dead code paths

**Acceptance Criteria:**
- [ ] No tmux imports in `cli.py`
- [ ] No hand imports in `cli.py`
- [ ] `kd chat` not in `--help` output
- [ ] `kd attach` not in `--help` output
- [ ] `kd --help` works without errors
- [ ] Existing tests pass (or are updated)

---

### T2: Delete tmux module and tests
**Priority:** 0
**Dependencies:** T1

Delete legacy tmux orchestration code:
- Delete `src/kingdom/tmux.py`
- Delete `tests/test_tmux.py`

**Acceptance Criteria:**
- [ ] `src/kingdom/tmux.py` deleted
- [ ] `tests/test_tmux.py` deleted
- [ ] `kd --help` still works

---

### T3: Delete hand module
**Priority:** 0
**Dependencies:** T1

Delete legacy REPL code:
- Delete `src/kingdom/hand.py`

**Acceptance Criteria:**
- [ ] `src/kingdom/hand.py` deleted
- [ ] No import errors anywhere

---

## Phase 2: Restructure to Branch-Based

### T4: Add branch name normalization
**Priority:** 1
**Dependencies:** T1

Add utility functions to `state.py`:
- `normalize_branch_name(branch: str) -> str`
- `branches_root(base: Path) -> Path` - returns `.kd/branches/`
- `branch_root(base: Path, branch: str) -> Path` - returns `.kd/branches/<normalized>/`
- `backlog_root(base: Path) -> Path` - returns `.kd/backlog/`
- `archive_root(base: Path) -> Path` - returns `.kd/archive/`

Normalization rules:
- Replace `/` with `-`
- Lowercase
- Replace non-ASCII with `-` or strip
- Collapse multiple `-` into one
- Store original branch name in `state.json`: `{"branch": "feature/oauth-refresh"}`

Collision handling:
- Check if normalized directory already exists
- Error with clear message if collision detected
- Suggest resolution (e.g., use different name)

**Acceptance Criteria:**
- [ ] `normalize_branch_name("feature/oauth-refresh")` → `"feature-oauth-refresh"`
- [ ] `normalize_branch_name("JRB/Fix-Bug")` → `"jrb-fix-bug"`
- [ ] `normalize_branch_name("feat//double")` → `"feat-double"` (no double dashes)
- [ ] Collision detection works
- [ ] Unit tests for normalization edge cases

---

### T5a: Add new layout functions
**Priority:** 1
**Dependencies:** T4

Add new layout functions to `state.py` (additive, doesn't break existing):
- `ensure_base_layout()` creates `.kd/branches/`, `.kd/backlog/tickets/`, `.kd/archive/`, `.kd/worktrees/`
- `ensure_branch_layout(base, branch)` creates:
  - `.kd/branches/<normalized>/`
  - `design.md`, `breakdown.md`, `learnings.md`
  - `tickets/` directory
  - `logs/` directory (for council logs)
  - `sessions/` directory
  - `state.json`
- Preserve `config.json` at `.kd/` level

**Acceptance Criteria:**
- [ ] `ensure_base_layout()` creates new directory structure
- [ ] `ensure_branch_layout()` creates branch folder with all subdirs
- [ ] `logs/` and `sessions/` directories created for council
- [ ] `config.json` preserved
- [ ] Old functions still work (not removed yet)

---

### T5b: Update gitignore patterns
**Priority:** 1
**Dependencies:** T5a

Update `.kd/.gitignore` template for new structure:
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

**Acceptance Criteria:**
- [ ] New gitignore template in `ensure_base_layout()`
- [ ] Correctly ignores state.json but tracks design.md, tickets/*.md
- [ ] Test that `git status` is clean after operations

---

### T6: Update kd start command
**Priority:** 1
**Dependencies:** T5a, T5b

Update `kd start <branch>` to use new structure:
- If no argument: use current git branch name
- Normalize branch name for directory
- Check for collision before creating
- Create `.kd/branches/<normalized>/`
- Set `.kd/current` to normalized name
- Store original branch name in `state.json`
- Optionally create git branch if it doesn't exist (with `--create-branch` flag)

Edge cases:
- Detached HEAD with no arg → error with helpful message
- Branch doesn't exist → prompt or use `--create-branch`
- `.kd/current` already set → warn and confirm, or use `--force`

Remove all tmux session creation.

**Acceptance Criteria:**
- [ ] `kd start feature/oauth` creates `.kd/branches/feature-oauth/`
- [ ] `state.json` contains `{"branch": "feature/oauth"}`
- [ ] `.kd/current` contains `feature-oauth`
- [ ] No tmux references
- [ ] Works with current git branch if no arg
- [ ] Handles detached HEAD gracefully
- [ ] Handles existing current gracefully

---

### T7: Update kd done command
**Priority:** 1
**Dependencies:** T6

Update `kd done` to archive completed branches:
- Move `.kd/branches/<name>/` to `.kd/archive/<name>/`
- If archive already exists, add timestamp suffix
- Clear `.kd/current`
- Update state.json with `done_at` timestamp and `status: done`
- Clean up associated worktrees in `.kd/worktrees/`

**Acceptance Criteria:**
- [ ] `kd done` moves branch folder to archive
- [ ] `.kd/current` is cleared
- [ ] Archived folder preserves all content
- [ ] Worktrees cleaned up
- [ ] Handles archive collision (adds suffix)

---

### T8: Update kd status command (basic)
**Priority:** 1
**Dependencies:** T6

Update `kd status` for new structure (basic version without ticket counts):
- Show normalized branch name (from `.kd/current`)
- Show original git branch name (from state.json)
- Show design.md exists/empty status
- Show breakdown.md exists/empty status
- Remove tk subprocess calls

Ticket counts will be added in T8b after ticket module exists.

**Acceptance Criteria:**
- [ ] Shows normalized and original branch names
- [ ] Shows design/breakdown status
- [ ] Works with `--json` flag
- [ ] No tk subprocess calls

---

### T9: Simplify kd peasant command
**Priority:** 2
**Dependencies:** T6

Update `kd peasant` to just create worktree:
- Create worktree at `.kd/worktrees/<ticket-id>/`
- Check out a ticket branch: `<original-branch>/<ticket-id>`
- Print instructions for user to run their agent
- No tmux window creation

Add worktree tracking to enable cleanup:
- Record worktree in branch's state.json
- `kd peasant --clean <ticket-id>` to remove worktree

**Acceptance Criteria:**
- [ ] Creates worktree in correct location
- [ ] Creates appropriate ticket branch
- [ ] Prints helpful instructions
- [ ] No tmux references
- [ ] Worktree tracked in state.json
- [ ] `--clean` flag removes worktree

---

### T5c: Remove old layout functions
**Priority:** 2
**Dependencies:** T6, T7, T8, T9

Remove deprecated functions after all callers updated:
- Remove `runs_root()`, `run_root()`, `ensure_run_layout()`
- Or rename to `_deprecated_*` with warning
- Update any remaining callers

**Acceptance Criteria:**
- [ ] Old functions removed or deprecated
- [ ] No callers of old functions
- [ ] All tests pass

---

### T-migrate-runs: Migrate existing .kd/runs/
**Priority:** 2
**Dependencies:** T5a

Handle existing `.kd/runs/` directories:
- Detect if `.kd/runs/` exists on any kd command
- Provide `kd migrate` command to move:
  - `.kd/runs/<name>/` → `.kd/branches/<name>/`
- Preserve all content (design.md, breakdown.md, etc.)
- After migration, remove empty `.kd/runs/`

**Acceptance Criteria:**
- [ ] `kd migrate` moves runs to branches
- [ ] Content preserved exactly
- [ ] Warning shown if `.kd/runs/` detected
- [ ] Empty `.kd/runs/` removed after migration

---

## Phase 3: Integrate Ticket Management

### T10a: Create ticket model
**Priority:** 1
**Dependencies:** T5a

Create `src/kingdom/ticket.py` with core data model:
- `Ticket` dataclass with all fields (id, status, deps, links, created, type, priority, assignee, title, description, acceptance)
- `generate_ticket_id()` - generates `kin-xxxx` format, checks for collision
- `parse_ticket(content: str) -> Ticket` - parse YAML frontmatter + markdown
- `serialize_ticket(ticket: Ticket) -> str` - write YAML frontmatter + markdown
- `read_ticket(path: Path) -> Ticket`
- `write_ticket(path: Path, ticket: Ticket)`

Ticket format (same as current tk):
```yaml
---
id: kin-a1b2
status: open
deps: []
links: []
created: 2026-02-04T16:00:00Z
type: task
priority: 2
assignee: null
---
# Title

Description

## Acceptance Criteria
- [ ] Criterion
```

**Acceptance Criteria:**
- [ ] Ticket dataclass defined
- [ ] Can parse existing tk ticket files
- [ ] Can serialize back to same format
- [ ] ID generation doesn't collide with existing
- [ ] Unit tests for parsing edge cases

---

### T10b: Add ticket management functions
**Priority:** 1
**Dependencies:** T10a

Add management functions to `ticket.py`:
- `list_tickets(directory: Path) -> list[Ticket]` - list all tickets in dir
- `find_ticket(base: Path, ticket_id: str) -> Path | None` - find by ID or partial ID across all locations (branches, backlog, archive)
- `move_ticket(ticket_path: Path, dest_dir: Path)` - move ticket file
- `get_ticket_location(base: Path, ticket_id: str) -> str` - returns "backlog", branch name, or "archive/<name>"

**Acceptance Criteria:**
- [ ] Can list tickets in any directory
- [ ] Partial ID matching works (e.g., `a1b` matches `kin-a1b2`)
- [ ] Can find tickets across branches, backlog, archive
- [ ] Can move tickets between locations
- [ ] Unit tests for all functions

---

### T11a: Add ticket CLI - core CRUD
**Priority:** 1
**Dependencies:** T10b

Add typer subcommand group with core operations:
- `kd ticket create "title" [--backlog] [-p priority] [-t type]` - create ticket
- `kd ticket list [--all]` - list current branch tickets, or all
- `kd ticket show <id>` - display ticket (partial ID match)

**Acceptance Criteria:**
- [ ] `kd ticket create` works with all options
- [ ] `kd ticket list` shows current branch tickets
- [ ] `kd ticket list --all` shows all tickets with location
- [ ] `kd ticket show` displays full ticket
- [ ] Partial ID matching works

---

### T11b: Add ticket CLI - status changes
**Priority:** 1
**Dependencies:** T11a

Add status change commands:
- `kd ticket start <id>` - set status to in_progress
- `kd ticket close <id>` - set status to closed
- `kd ticket reopen <id>` - set status to open

**Acceptance Criteria:**
- [ ] All status commands work
- [ ] Status persisted to file
- [ ] Partial ID matching works

---

### T11c: Add ticket CLI - relationships and queries
**Priority:** 1
**Dependencies:** T11b

Add relationship and query commands:
- `kd ticket dep <id> <dep-id>` - add dependency
- `kd ticket undep <id> <dep-id>` - remove dependency
- `kd ticket move <id> <branch>` - move ticket to branch (or "backlog")
- `kd ticket ready` - list tickets ready to work (deps resolved, not closed)
- `kd ticket edit <id>` - open in $EDITOR

**Acceptance Criteria:**
- [ ] Dependency management works
- [ ] Move between branches works
- [ ] `ready` correctly filters by deps and status
- [ ] Edit opens correct file

---

### T8b: Add ticket counts to kd status
**Priority:** 2
**Dependencies:** T11a

Enhance `kd status` with ticket information:
- Show ticket counts (open, in_progress, closed)
- Show count of ready tickets
- Show currently assigned ticket if any

**Acceptance Criteria:**
- [ ] Ticket counts displayed
- [ ] Ready count displayed
- [ ] Works with `--json` flag

---

### T12: Migrate existing .tickets/
**Priority:** 2
**Dependencies:** T11a

Migration for existing tickets:
- Detect `.tickets/` directory on kd commands
- `kd migrate` moves all `.tickets/*.md` to `.kd/backlog/tickets/`
- Verify each ticket parses correctly before moving
- Report any parse failures
- Delete `.tickets/` only after successful migration

**Acceptance Criteria:**
- [ ] `kd migrate` handles .tickets/
- [ ] Parse verification before move
- [ ] Clear error reporting for failures
- [ ] Source only deleted after success
- [ ] Warning shown if `.tickets/` detected

---

### T13: Remove tk references
**Priority:** 2
**Dependencies:** T11c, T12

Remove all references to external tk tool:
- Update `kd breakdown --apply` to use internal ticket module
- Remove any tk subprocess calls
- Update any documentation referencing tk

**Acceptance Criteria:**
- [ ] No `tk` subprocess calls in codebase
- [ ] `kd breakdown --apply` creates tickets internally
- [ ] Grep for "tk " returns no hits in src/

---

## Phase 4: Documentation Cleanup

### T14: Archive old docs
**Priority:** 2
**Dependencies:** none (can run anytime)

Move outdated docs to `docs/archive/`:
- `docs/MVP.md`
- `docs/MVP-breakdown.md`
- `docs/mvp-next-step-design.md`
- `docs/dispatch-design.md`
- `docs/dispatch-cli-design-v2.md`
- `docs/design_breakdown_polish.md`
- `docs/designing_logs.md`
- `docs/tech-stack.md`
- `docs/install.md` (if outdated)

**Acceptance Criteria:**
- [ ] All listed docs moved to `docs/archive/`
- [ ] `docs/archive/` directory created
- [ ] Git history preserved (use `git mv`)

---

### T15: Update README and architecture docs
**Priority:** 2
**Dependencies:** T6, T11c

Update all user-facing documentation:

README.md:
- Explain branch-centric workflow
- Document key commands: `kd start`, `kd ticket`, `kd council`
- Remove third-party tk reference
- Add quick start guide

docs/cli-skill-architecture.md:
- Update directory structure examples to show `.kd/branches/`
- Remove tmux references
- Document integrated ticket management
- Mark as canonical architecture doc

docs/council-design.md:
- Remove any tmux references
- Verify examples still work

**Acceptance Criteria:**
- [ ] README explains current architecture
- [ ] No references to tmux, hand, or external tk
- [ ] cli-skill-architecture.md reflects implementation
- [ ] Includes example workflow
- [ ] All docs consistent with each other

---

## Dependency Graph

```
T0 (fix gitignore)
 └──> T1 (remove from CLI)
       ├──> T2 (delete tmux.py)
       ├──> T3 (delete hand.py)
       └──> T4 (normalization)
             └──> T5a (new layouts)
                   ├──> T5b (gitignore patterns)
                   ├──> T-migrate-runs (migrate .kd/runs/)
                   ├──> T6 (kd start) ──────────────────────┐
                   │     ├──> T7 (kd done)                  │
                   │     ├──> T8 (kd status basic)          │
                   │     └──> T9 (kd peasant)               │
                   │           └──> T5c (remove old funcs)  │
                   │                                        │
                   └──> T10a (ticket model)                 │
                         └──> T10b (ticket management)      │
                               └──> T11a (ticket CRUD) ─────┤
                                     ├──> T11b (status)     │
                                     │     └──> T11c (rels) │
                                     │           └──> T13 (remove tk)
                                     ├──> T8b (status + tickets)
                                     └──> T12 (migrate .tickets/)

T14 (archive docs) ──> (no deps, anytime)

T6 + T11c ──> T15 (update docs)
```

## Summary

- **21 tickets** total (up from 16 after splits)
- **Phase 1:** 4 tickets (T0, T1, T2, T3)
- **Phase 2:** 8 tickets (T4, T5a, T5b, T5c, T6, T7, T8, T9, T-migrate-runs)
- **Phase 3:** 7 tickets (T10a, T10b, T11a, T11b, T11c, T8b, T12, T13)
- **Phase 4:** 2 tickets (T14, T15)

**Critical path:** T0 → T1 → T4 → T5a → T6 → T10a → T10b → T11a → T11c → T13 → T15

**Parallelization opportunities:**
- T2, T3 can run in parallel after T1
- T5b, T6, T10a can run in parallel after T5a
- T7, T8, T9 can run in parallel after T6
- T11b, T11c can run in parallel after T11a
- T14 can run anytime
