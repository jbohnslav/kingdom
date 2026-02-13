---
from: claude
to: king
timestamp: 2026-02-13T23:39:55Z
---

Good. I now have a comprehensive view. Here's my review:

---

## Review: Implementation vs Design

### (1) Does the implementation match the design?

**Yes, with good fidelity across all implemented themes.** Specifically:

| Design Item | Status | Notes |
|---|---|---|
| **kin-a321**: `kd done` status-only | Implemented | `shutil.move` removed, sets `status: done` in state.json, clears pointer, cleans worktrees. No archive move. |
| **kin-b504**: Design approved in `kd status` | Implemented | `design_approved` read from state.json, displayed as `(approved)` suffix. |
| **kin-db3b**: Council sync default | Implemented | Flipped: default is now sync (in-process blocking). `--async` is opt-in. |
| **kin-b43e**: Progress indicator on watch | Implemented | Spinner with `[Ns] Waiting for: member1, member2...` that updates. |
| **kin-09c9**: @mentions | Implemented | `@member` parsed via regex, `@all` supported, unknown mentions fail loudly. `--to` overrides mentions. |
| **kin-b76b**: Assignee tracking | Implemented | `tk assign`, `tk unassign`, `tk show` (no-arg → hand), `tk list` shows assignee, `peasant start` auto-assigns. |
| **kin-8393**: tk move variadic + `--to` | Implemented | Variadic `ticket_ids`, `--to` flag, backwards-compat heuristic for 2-arg case. |
| **kin-98e7**: Drop kin- prefix + migrate | Implemented | `generate_ticket_id` returns bare hex. `kd migrate --dry-run` renames files + rewrites frontmatter. |
| Done branch filtering | Implemented | `is_branch_done()` helper. `tk list --all` and `tk ready` skip done branches. |

### (2) Bugs and edge cases

**Bug 1 — `kd migrate` doesn't use `git mv`** (design says it should)

The design explicitly states: *"Migration uses `git mv` to preserve file history"* and *"Uses `git mv` for history."* But the implementation at `cli.py:2016` uses `ticket_file.rename(new_path)` — a plain Python rename. This loses git history for the renamed files. This is the most significant gap between design and implementation.

**Bug 2 — `kd migrate` regex may be too greedy**

The regex `r"\bkin-([0-9a-f]{4})\b"` at `cli.py:2023` will match `kin-` followed by exactly 4 hex chars anywhere in a ticket file's body text, not just frontmatter fields. If a ticket body discusses another ticket by ID (e.g., "see kin-a1b2 for context"), that's fine — you want it rewritten. But if someone writes prose like "kin-dead is a poor choice" where `dead` happens to be 4 hex chars, it'll get rewritten to just `dead`. Edge case, but worth noting. Probably acceptable in practice.

**Bug 3 — `kd migrate` dry-run message says `--no-dry-run`**

At `cli.py:2032`: `"Dry run complete. Use --no-dry-run to apply changes."` But there's no `--no-dry-run` flag. The actual invocation without dry-run is just `kd migrate` (dry_run defaults to False). The message should say something like `"Dry run complete. Run without --dry-run to apply."`.

**Bug 4 — `kd migrate` doesn't rewrite `state.json` ticket mappings**

The `breakdown --apply` command writes a `tickets` dict to `state.json` mapping breakdown IDs to ticket IDs (e.g., `{"T-001": "kin-abc123"}`). The migrate command only rewrites `.md` files, not JSON. Those state.json refs will have stale `kin-` prefixed IDs. Since state.json is gitignored this is low-impact, but any code reading `state["tickets"]` values will get wrong IDs post-migration.

**Bug 5 — `find_ticket` still searches `.kd/archive/`**

At `ticket.py:327-333`, `find_ticket` still iterates `archive/*/tickets/`. Since `kd done` no longer moves branches to archive, this code is dead for new workflows. But it's harmless for backwards compat with pre-existing archives, so this isn't really a bug — just vestigial code.

**Edge case — `tk move` backwards-compat heuristic is fragile**

At `cli.py:2458-2468`, the 2-arg backwards-compat logic tries `find_ticket` on the second arg. If it happens to match a ticket AND was intended as a branch name, it silently does the wrong thing (tries to move two tickets instead of one ticket to a target). The risk is low because branch names rarely look like ticket IDs, but it's worth calling out.

**Edge case — `@mentions` regex matches in code blocks**

The design says: *"Parser must avoid false positives on `@` in code blocks or email addresses."* The implementation at `cli.py:313` uses `re.findall(r"(?<!\w)@(\w+)", prompt)`. This does handle word-boundary prefixes (won't match `email@domain`), but won't handle code blocks like `` `@member` ``. In practice this is unlikely to matter since council prompts are conversational, not code.

### (3) Migration command and backwards compat

**Migration is well-scoped** — it correctly scans backlog, all branches, and archive. The two-pass approach (rename files first, then rewrite content) is correct.

**Backwards compat in `find_ticket` is solid** — the search strips `kin-` from input if present (`cli.py:297-299`), and matches both `file_id_suffix` and `kin-{search_id}` forms (`ticket.py:346`). Users can type either `a1b2` or `kin-a1b2` and it'll find the right ticket regardless of whether migration has run.

**Backwards compat in `generate_ticket_id` is solid** — collision check looks for both `{id}.md` and `kin-{id}.md` (`ticket.py:90-92`).

**`tk pull` has proper backwards compat** — tries both `{clean_id}.md` and `kin-{clean_id}.md` (`cli.py:2537-2540`).

### (4) Things to fix before merging

**Must fix:**
1. **`kd migrate` should use `git mv`** instead of `Path.rename()`. The design explicitly requires it for history preservation. This is a one-line change per rename.
2. **Fix the dry-run message** — `--no-dry-run` doesn't exist as a flag.

**Should fix:**
3. **Add a test for `kd migrate`** — I don't see any test coverage for the migrate command. Given it's described as "high blast radius" in the design, it should have at least basic test coverage (dry-run output, actual rename+rewrite, idempotency).

**Nice to have (not blocking):**
4. The `kd done` idempotency test (`test_done.py:150-168`) is good — confirms running done twice works. But there's no test that `kd start` rejects or warns about starting a session on a done branch. The design says "CLI commands filter done branches by default" — `kd start` isn't covered.
5. Consider adding `--include-done` flag to `tk list --all` as the design mentions, for when users need to see archived work. Currently done branches are silently filtered with no way to override.
