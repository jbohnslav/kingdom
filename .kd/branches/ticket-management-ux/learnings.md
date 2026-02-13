# Learnings: ticket-management-ux

## kd Workflow for Agents (How to Use the CLI)

### Branch lifecycle
1. `git checkout -b <branch> master` — create feature branch
2. `kd start` — initialize the run (creates `.kd/branches/<branch>/`)
3. `kd design` — creates design.md template, prints path
4. Edit design.md with goals, requirements, decisions
5. `kd council ask "..."` — get council feedback (async by default, watches for responses)
6. Move tickets from backlog: `kd tk move <id> <branch>`
7. Work tickets: `kd tk start <id>`, make changes, `kd tk close <id>`
8. `kd done` — archive the branch when complete

### Ticket commands
- `kd tk create "title"` — create ticket, prints absolute path for editing
- `kd tk list` — list tickets on current branch
- `kd tk list --backlog` — list backlog tickets
- `kd tk ready` — list tickets ready to work (open, deps resolved)
- `kd tk show <id>` — show ticket details
- `kd tk start/close/reopen <id>` — change ticket status
- `kd tk move <id> <branch>` — move ticket to another branch
- `kd tk edit <id>` — open in $EDITOR
- `kd tk dep <id> <depends-on>` — add dependency

### Council commands
- `kd council ask "prompt"` — dispatch to all members, watch for responses
- `kd council ask "prompt" --to claude` — ask a single member
- `kd council watch` — watch current thread for responses
- `kd council threads` — list threads
- `kd council read <thread-id>` — read thread messages

### Peasant commands (background agents)
- `kd peasant start <ticket-id>` — launch agent in worktree
- `kd peasant start <ticket-id> --hand` — launch in current checkout (serial)
- `kd peasant status` — show running peasants
- `kd peasant logs <ticket-id>` — show agent logs
- `kd peasant stop <ticket-id>` — stop a running peasant
- `kd peasant review <ticket-id>` — review work, `--accept` or `--reject "msg"`
- `kd work <ticket-id>` — run agent loop directly (foreground)

### Things learned during this run
- `kd tk move` is needed to pull backlog tickets into a branch before `kd tk pull` exists
- Council `ask` is async by default — dispatches background workers, then watches
- The `.venv` only needs to be sourced once per shell session
- Design doc should be written before asking council — they read the file
- Tickets in backlog use global `find_ticket` — scoped search only applies via `_resolve_peasant_context`
