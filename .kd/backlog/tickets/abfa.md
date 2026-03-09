---
id: "abfa"
status: open
deps: []
links: []
created: 2026-03-09T01:18:45Z
type: bug
priority: 2
---
# Dirty .kd/ files shouldn't block peasant accept or start

Both `kd peasant accept` and `kd peasant start` require a clean working tree, but `.kd/` ticket files are almost always dirty (from `kd tk log`, status changes, AC edits, etc. done moments before). This forces pointless commit cycles.

## peasant accept
1. Edit ticket (kd tk log, update AC, etc.)
2. git add + commit just to satisfy the clean-tree check
3. kd peasant accept
4. Accept modifies the ticket again (closes it)
5. git add + commit again

Two commits of pure ticket bookkeeping just to run accept.

## peasant start
Worktree-based peasants are created from the last commit. If `.kd/` files are dirty, the warning fires and the peasant won't have the latest ticket content. You have to commit ticket updates before launching, even though the peasant will read them from the branch anyway.

## Options
- Auto-stash `.kd/` changes before merge, restore after
- Exclude `.kd/` from the dirty-tree check (it's never code)
- Auto-commit `.kd/` changes as part of the accept/start flow

## Acceptance Criteria

- [ ] kd peasant accept succeeds even when .kd/ ticket files have uncommitted changes
- [ ] kd peasant start succeeds (or auto-commits .kd/) when only .kd/ files are dirty
