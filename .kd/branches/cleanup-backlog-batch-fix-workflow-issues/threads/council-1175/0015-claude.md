---
from: claude
to: king
timestamp: 2026-02-14T00:29:46Z
---

OK. Here's the full review.

---

## Review: Post-Fix Changes

### Migrate Command Fixes (7606285)

All three issues from last review are resolved:

1. **`--apply` flag** — Correct. Default is now dry-run, `--apply` executes. The dry-run message (`"Run with --apply to execute."`) is accurate.

2. **Collision preflight** — Solid. Scans all ticket dirs for name collisions *before* any renames happen (lines 2012-2024). Aborts with exit code 1 and lists the conflicting files. Test `test_collision_aborts` covers this.

3. **`git mv`** — Implemented at line 2036-2042 with a sensible fallback: tries `git mv` first, falls back to `Path.rename()` if it fails (e.g., not a git repo). This is the right approach for tests running in `isolated_filesystem()` where git may not be initialized.

### `--include-done` Flag (tk list)

Clean implementation at line 2185:
```python
if branch_dir.is_dir() and (include_done or not is_branch_done(branch_dir)):
```

Only takes effect with `--all`. Without `--all`, listing the current branch isn't affected (correct — if you're on a done branch and explicitly looking at it, you should see its tickets).

### Migrate Tests

Four tests, good coverage:

| Test | What it covers |
|---|---|
| `test_dry_run_shows_changes` | Default (no `--apply`) shows plan, doesn't modify files |
| `test_apply_renames_and_rewrites` | File renamed, frontmatter `id:` rewritten, deps rewritten, body references rewritten |
| `test_apply_is_idempotent` | Second run reports "0 files renamed" — no crash, no double-rewrite |
| `test_collision_aborts` | Pre-existing target file → exit code 1 with error message |

### Migration Commit (22a348e)

128 files renamed, 128 files rewritten. Git rename detection works — `git log --follow` correctly traces through the rename (I verified on `db3b.md`). One file (`kin-db3b.md`) shows as add/delete in `--stat` output because the content similarity dropped below the default threshold (both filename and `id:` field changed), but `--follow` handles it. This is a git display quirk, not a data loss issue.

### Issues Found

**One thing to fix:**

The `kin-b202.md` worklog got its worktree paths rewritten by the migrate regex. In the migration diff:

```
-rootdir: /Users/jrb/code/kingdom/.kd/worktrees/kin-b202
+rootdir: /Users/jrb/code/kingdom/.kd/worktrees/b202
```

The regex `\bkin-([0-9a-f]{4})\b` matched `kin-b202` inside absolute file paths in the ticket body text and rewrote them. Those paths are historical log entries — they'll never be used again, but they're now inaccurate (the worktree *was* at `kin-b202`, not `b202`). This is the "greedy regex in body text" edge case I flagged last review. It's cosmetic and non-functional, but it's there.

**Not a bug, just noting:** The regex also wouldn't match `kin-` followed by 5+ hex chars (it's anchored to exactly 4 with `\b`). So references like `kin-abc123` in state.json ticket mappings wouldn't be affected even if state.json weren't gitignored. Good.

### Remaining `kin-` references in source code

All appropriate. They fall into three categories:

1. **Backwards compat** in `find_ticket` and `tk pull` — strips `kin-` prefix from user input, checks both filename formats. This is the right approach for a gradual migration.
2. **Collision checking** in `generate_ticket_id` — checks both `{id}.md` and `kin-{id}.md`. Correct.
3. **The migrate command itself** — naturally references `kin-` since that's what it's migrating from.
4. **Docstrings/comments** — reference the old format as examples. Low priority to update but not wrong.

### Verdict

The fixes from last review are all correctly implemented. Tests pass. The migration ran clean across 128 files with history preserved. The `--include-done` flag is wired correctly.

The only remaining item from the design that I can see as incomplete: **tests still use `kin-` prefixed IDs throughout** (`test_ticket.py` creates tickets with `id="kin-test"`, `id="kin-a1b2"`, etc.). These tests work fine because `parse_ticket` doesn't validate ID format — it just stores whatever string is in the frontmatter. So they're not broken, but they test the legacy format rather than the new one. If you want the test suite to reflect the post-migration world, a sweep to remove `kin-` from test fixtures would be a nice cleanup. Not blocking.
