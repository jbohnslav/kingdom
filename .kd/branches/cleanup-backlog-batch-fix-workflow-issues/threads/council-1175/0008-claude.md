---
from: claude
to: king
timestamp: 2026-02-13T23:12:02Z
---

Good. Now I have a clear picture. Let me lay out the tradeoffs.

---

## Analysis

The core tension: `kd done` moves tracked files (design.md, tickets/, threads/) from `branches/` to `archive/`, producing git changes. If you've already merged your feature branch and are back on master, you can't commit those changes with branch protection on.

### Option 3: Run `kd done` on the feature branch before merge

**This is the right answer.** Here's why:

The archive changes *are part of the feature's work*. The design doc, council threads, tickets, and learnings all belong to that branch's PR. Archiving them before merge means:

- The PR includes the full lifecycle: branch created → work done → branch archived
- No orphaned git changes on master after merge
- No new infrastructure needed (no gc, no gitignore hacks)
- The archive commit is reviewable in the PR like everything else
- `kd done` becomes part of the "wrap up" phase, same as closing tickets

**The workflow becomes:** close tickets → `kd done` → commit `.kd/` changes → push → merge PR

**One concern you might have:** "but what if I need the branch state while the PR is still open?" That's solvable — `kd done` already sets `status: done` in state.json before moving. You could split it into two steps: a soft `kd done` that sets status and cleans up worktrees (safe to run while PR is pending), then the archive move happens either as part of the same command or as a separate `kd archive` step. But honestly, if you're running `kd done`, you're done. The PR is ready. Archive it, commit, push, merge.

### Why the other options are worse

**Option 1 (status-only, accept clutter):** You'd need to update every command that lists/reads branches to filter by status. `kd start` listing, `kd tk list`, `kd design` — they'd all need "skip done branches" logic. The `.kd/branches/` directory becomes a junk drawer. And you lose the clean semantic of "branches/ = active, archive/ = done" which is immediately understandable from the filesystem alone. The `kd gc` escape hatch just defers the same problem (moving files on master).

**Option 2 (gitignore archive):** You lose the history. The whole point of archiving is preserving the design docs, council threads, and ticket records *in the repo*. If archive is gitignored, that knowledge disappears when you clone fresh or switch machines. It undermines the value of tracking `.kd/` in git at all.

**Option 4 ("something else"):** The only variant worth considering is a hybrid: `kd done` does the archive move on the feature branch, but if you forget and run it on master, it falls back to a status-only approach and prints a warning. That gives you the clean path (option 3) with a graceful degradation. But I'd keep this simple — just make option 3 the documented workflow and don't over-engineer the fallback.

### Recommendation

**Go with option 3. Add a check to `kd done` that warns if you're on master/main.** Something like:

```
⚠ You're on 'master'. Run 'kd done' on your feature branch so archive
  changes are included in the PR. Use --force to archive anyway.
```

That's it. No new infrastructure, no status field changes, no gc command. The archive directory move works great — it just needs to happen at the right point in the workflow.
