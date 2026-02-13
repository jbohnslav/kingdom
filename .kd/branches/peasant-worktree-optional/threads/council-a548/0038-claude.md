---
from: claude
to: king
timestamp: 2026-02-13T17:43:50Z
---

OK, I now have the full picture. Here's my analysis of each finding.

---

## Verdict on PR #6 Review Findings

### Critical / P1

**#1 — Worktree path inside repo: DISAGREE**

`.kd/worktrees/` is in the `.gitignore` (line 8). Git doesn't reject nested worktrees — it rejects worktrees *inside another worktree's tracked tree*. Since `worktrees/` is gitignored, git won't try to track it. The `git worktree add` command at line 892/898 creates a worktree *pointing to* that path with its own branch checkout. This works — git worktree only cares that the *target path* isn't already a worktree, not that it's physically nested. I've seen this pattern work in practice. That said, some git operations (like `git clean -fdx`) could accidentally nuke worktrees since they're under the repo root. Low risk, but placing them under a temp dir or `~/.kd-worktrees` would be more robust. **Downgrade to P2 at most.**

**#2 — Message sequencing race: AGREE, but low practical risk**

`next_message_number()` + write is indeed non-atomic. Two concurrent peasants writing to the *same* thread could collide. In practice, work threads are 1 peasant + 1 king, so collisions require the king to send a directive at the exact moment the peasant writes. The council thread is the more realistic risk — parallel member responses in `--sync` mode use `ThreadPoolExecutor` and all call `add_message`. Worth fixing with `O_EXCL` or a retry loop. **Agree P1 for council, P2 for work threads.**

**#3 — Backlog auto-move on read ops: AGREE, real bug**

`_resolve_peasant_context` is called by `peasant logs`, `peasant read`, `peasant stop`, `peasant clean`, `peasant sync` — all read-only or operational commands that should not move a ticket. Running `kd peasant logs kin-d5ae` on a backlog ticket would silently yank it into the branch. The auto-pull should only happen in `peasant_start` and `kd work`, not in the shared resolver. **Agree P1.**

**#4 — Missing worktree falls back to base: AGREE**

`peasant_review --reject` at line 1546-1548 silently falls back to `base` if the worktree directory is gone. This means the relaunched agent works on the main checkout instead of the ticket branch — silently doing work in the wrong place. Should fail with "Worktree missing, re-create with `kd peasant start`" or at least warn loudly. **Agree P1.**

**#5 — Council watch vs `--to` mismatch: AGREE**

`council_watch` reads `expected_members` from `meta.members` (line 594). When you `--to codex` on a thread whose metadata lists `[claude, codex, cursor, king]`, watch waits for all three agents. The worker only queries codex. Watch blocks until timeout. **Agree P1.** Fix: pass expected members as a parameter, or have watch infer from the latest king message's `to` field.

**#6 — Parallel `--hand` workers on same checkout: AGREE**

The guard at line 1086 checks `session_name = f"peasant-{full_ticket_id}"` — it only detects if *this specific ticket* is already being worked on. Two different tickets can both be launched with `--hand` and they'll both operate on the same working directory concurrently, interleaving edits and commits. Should either block (only one `--hand` at a time) or warn. **Agree P1.**

### High / P2

**#7 — Timezone-naive datetime crash: DISAGREE (for current code)**

Line 132-133 converts `Z` suffix to `+00:00` before calling `fromisoformat()`. The `else` branch (line 136) uses `datetime.now(UTC)` which is aware. The `Ticket` default factory also uses `datetime.now(UTC)`. So all tickets created by kingdom are aware. The only way to get a naive datetime is from a hand-edited ticket file with a bare ISO string like `2026-02-13T14:00:00` (no Z, no offset). `fromisoformat` on Python 3.12 *will* return naive in that case, and sorting would mix naive/aware and raise `TypeError`. **This is technically valid but requires malformed input.** I'd call it P3 — add UTC assumption for bare timestamps.

**#8 — Empty branch name from normalization: AGREE**

`normalize_branch_name("中文")` → NFKD decomposes → ascii encode drops everything → empty string → `.kd/branches/` root. This would write state to the branches directory itself. Trivial to fix with a guard. **Agree P2.**

**#9 — Council preamble mentions mutating command: DISAGREE**

The preamble says "run `kd design` to find it." `kd design` without arguments just creates a template *if the file doesn't exist* and is essentially a `show` command. It prints the path. It's not destructive. And the preamble explicitly says "Do NOT modify source code, tests, configs, or any other files unless the King explicitly asks you to." The risk is near zero. **Disagree, drop it.**

**#10 — Watch timeout boundary: AGREE, low impact**

If the worker finishes a member response at second 299 of a 300s timeout, watch may already be exiting. Adding a small buffer (e.g., `timeout + 30`) to watch is trivial. **Agree P2, easy fix.**

**#11 — Interactive `kd work` ignores `--base`: ALREADY FIXED**

The design doc's "Issues Found" section listed this, and it was fixed — `_resolve_peasant_context(ticket_id, base=base)` at line 1683 now passes `base`. **Drop it.**

**#12 — `$EDITOR` with flags breaks ticket edit: AGREE**

Line 2346: `subprocess.run([editor, str(ticket_path)])` where `editor = os.environ.get("EDITOR", "vim")`. If `EDITOR="code --wait"`, this passes `"code --wait"` as a single argv[0], which fails with `FileNotFoundError`. Should be `shlex.split(editor) + [str(ticket_path)]`. **Agree P2, trivial fix.**

**#13 — Concurrent write collision in `write_json`: DISAGREE (mostly)**

Line 149 uses `path.with_suffix(f".{os.getpid()}.tmp")`. Two threads in the same process could collide, but kingdom doesn't use threads for JSON writes — each peasant is a separate process. Two processes with different PIDs won't collide. The only risk is two threads in `council.py`'s `ThreadPoolExecutor`, but those save sessions *after* all queries complete, not concurrently. **Disagree for practical purposes.** Adding a thread ID is harmless though.

### Medium

**#14 — Codex workflow duplicate comments: N/A**

No `.github/workflows/codex.yml` exists in this repo. **Drop it — phantom finding.**

**#15 — Council watch `expected_members` on reused thread: AGREE, duplicate of #5**

This is the same root cause as #5 — `expected_members` comes from thread metadata, not the current query scope. **Merge with #5.**

---

## Summary: What to actually fix

| # | Finding | Verdict | Priority |
|---|---------|---------|----------|
| 1 | Nested worktrees | Disagree (gitignored, works) | Drop or P3 |
| 2 | Message sequencing race | Agree (council path) | P1 |
| 3 | Backlog auto-move on reads | **Agree, real bug** | P1 |
| 4 | Missing worktree fallback | **Agree** | P1 |
| 5+15 | Watch vs `--to` mismatch | **Agree** | P1 |
| 6 | Parallel `--hand` conflict | **Agree** | P1 |
| 7 | Naive datetime | Disagree (requires bad input) | P3 |
| 8 | Empty branch name | Agree | P2 |
| 9 | Preamble wording | Disagree | Drop |
| 10 | Watch timeout buffer | Agree | P2 |
| 11 | `--base` ignored | Already fixed | Drop |
| 12 | `$EDITOR` with flags | Agree | P2 |
| 13 | `write_json` collision | Disagree (processes have unique PIDs) | Drop |
| 14 | Codex workflow | File doesn't exist | Drop |

**Four P1 bugs worth fixing now:** #3, #4, #5, #6. **Three P2 improvements:** #8, #10, #12. The rest are phantom findings, already fixed, or edge cases that can wait.
