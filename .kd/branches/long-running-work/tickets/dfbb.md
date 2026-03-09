---
id: "dfbb"
status: closed
deps: []
links: []
created: 2026-03-03T20:57:00Z
type: bug
priority: 2
assignee: peasant-dfbb
---
# Council threads lost after branch archive — can't resume cross-session chats

Council threads are stored under the branch directory (`.kd/branches/<branch>/threads/`). When a branch is archived via `kd done`, threads go with it. Trying to resume a thread from an archived branch fails with "Thread not found" even though the data still exists in `.kd/archive/`.

Repro:
1. `kd council ask "question"` on branch A (creates thread council-fafc)
2. `kd done` branch A (archives to .kd/archive/)
3. `kd start` on branch B
4. `kd council chat council-fafc` → "Thread not found"

## Acceptance Criteria

- [ ] `kd council show <thread-id>` finds threads in archived branches when not found on the active branch
- [ ] `kd council chat <thread-id>` can view archived threads (read-only — cannot append new messages)
- [ ] `kd council list --all` shows threads across all branches including archived ones
- [ ] Archived threads are clearly labeled as such in output (e.g. "[archived]" or source branch shown)
- [ ] No changes to active branch thread behavior — only adds archive fallback

## Worklog

- [08:11] — Iteration 1/50 — calling agent
  Ticket: Council threads lost after branch archive — can't resume cross-session chats
- 2026-03-06 08:47 — Implemented archive thread fallback. Changes: thread.py (ThreadLocation dataclass, resolve_thread_globally, list_all_threads, list_messages_from_dir helpers), council.py CLI (resolve_council_thread_location for show/chat archive fallback, council list --all flag, archived thread labels, read-only chat for archived threads). 5 new tests added. Full suite passes (1673 passed).
- [08:48] — Now let me check how archiving works and the state module for `branch_root`.Good, I now have a clear picture. The archive directory at `.kd/archive/` mirrors the branch structure and contains threads. I need to add fallback search across all branches and archive. Let me plan and implement.First, ...
- [08:48] — Files changed:
  src/kingdom/cli/council.py | 281 +++++++++++++++++++++++++++++++++++++--------
   src/kingdom/thread.py      | 130 ++++++++++++++++++++-
   tests/test_cli_council.py  | 107 +++++++++++++++++
   3 files changed, 466 insertions(+), 52 deletions(-)
- [08:50] — Council review: APPROVED — awaiting king review
  [claude] APPROVED: Now let me run the tests.All 1673 pass. Now let me check the `council list --all` path for something — it dropped the member status symbols in the `--all` view.I noticed the `--all` view omits member status symbols (the ✓/○/✗/… indicators). Let me also look at the significant code duplication between the two `council list` paths and between `topic_for_thread` and `topic_for_location`.I notice `topic_for_location` uses `"..."` (three dots) while `topic_for_thread` and the inline topi...
