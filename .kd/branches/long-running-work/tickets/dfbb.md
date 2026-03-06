---
id: "dfbb"
status: open
deps: []
links: []
created: 2026-03-03T20:57:00Z
type: bug
priority: 2
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
