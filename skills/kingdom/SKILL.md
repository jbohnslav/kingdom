---
name: kingdom
description: >
  Multi-agent design and development workflow using the kd CLI.
  Manages design, breakdown, tickets, council consultation (multi-model
  perspectives), and peasant workers. Use when starting a new feature
  branch, breaking down work into tickets, consulting multiple AI models
  for design decisions, or managing development workflow with kd commands.
  Requires the kd CLI to be installed and on PATH.
compatibility: Requires Python 3.10+, kd CLI (uv tool install kingdom), git
---

You assist the developer (the "King") using the `kd` CLI for AI-assisted software development.

## Prerequisites

Install the kd CLI:

```bash
uv tool install kingdom    # or: pip install kingdom
```

Verify installation:

```bash
kd --help                  # confirm kd is on PATH
kd doctor                  # check agent CLIs are available
```

## Core Workflow

Every feature follows this lifecycle:

```
git checkout -b <branch>
kd start                   # initialize branch session
kd design                  # create design doc template
```

1. **Design** — Write the design doc at `.kd/branches/<branch>/design.md`. For major decisions, consult the council: `kd council ask "question"`. When ready: `kd design approve`.

2. **Breakdown** — Run `kd breakdown` to draft ticket breakdown. Review, then `kd breakdown --apply` to create tickets.

3. **Tickets** — Work through tickets: `kd tk start <id>`, do the work, `kd tk close <id>`. Use `kd tk ready` to see what's unblocked.

4. **Peasants** — For isolated ticket work, spawn a peasant: `kd peasant start <id>` (worktree) or `kd peasant start <id> --hand` (serial, current dir).

5. **Done** — When all tickets are closed: `kd done` to archive the branch.

Check status anytime with `kd status`.

## Command Reference

### Lifecycle

| Command | Description |
|---------|-------------|
| `kd init` | Initialize `.kd/` directory |
| `kd start` | Initialize branch session |
| `kd status` | Show branch, design, and ticket status |
| `kd done` | Archive branch and clear session |
| `kd doctor` | Check agent CLIs are installed |

### Design & Breakdown

| Command | Description |
|---------|-------------|
| `kd design` | Create design doc template |
| `kd design show` | Print design document |
| `kd design approve` | Mark design as approved |
| `kd breakdown` | Draft ticket breakdown |
| `kd breakdown --apply` | Create tickets from breakdown |

### Council

| Command | Description |
|---------|-------------|
| `kd council ask "prompt"` | Query all council members |
| `kd council ask --to <member> "prompt"` | Query one member |
| `kd council ask --new-thread "prompt"` | Start a fresh thread |
| `kd council ask --async "prompt"` | Dispatch in background, then watch |
| `kd council show <thread-id>` | Display a thread |
| `kd council list` | List all threads |
| `kd council watch <thread-id>` | Watch for incoming responses |
| `kd council reset` | Clear all sessions |

### Tickets

| Command | Description |
|---------|-------------|
| `kd tk list` | List tickets |
| `kd tk show <id>` | Show ticket details |
| `kd tk create "title"` | Create a ticket |
| `kd tk start <id>` | Mark in progress |
| `kd tk close <id>` | Mark complete |
| `kd tk reopen <id>` | Reopen a closed ticket |
| `kd tk ready` | Show tickets ready to work on |
| `kd tk edit <id>` | Open ticket in editor |
| `kd tk move <id> <branch>` | Move ticket to another branch |
| `kd tk pull <id>...` | Pull backlog tickets into current branch |
| `kd tk dep <id> <dep-id>` | Add dependency |
| `kd tk undep <id> <dep-id>` | Remove dependency |
| `kd tk assign <id> <agent>` | Assign to agent |
| `kd tk unassign <id>` | Clear assignment |

### Peasants

| Command | Description |
|---------|-------------|
| `kd peasant start <id>` | Launch peasant in worktree |
| `kd peasant start <id> --hand` | Launch in current dir (serial) |
| `kd peasant status` | Show active peasants |
| `kd peasant logs <id>` | Show peasant logs |
| `kd peasant stop <id>` | Stop a running peasant |
| `kd peasant clean <id>` | Remove peasant worktree |
| `kd peasant sync <id>` | Pull parent branch changes |
| `kd peasant msg <id> "text"` | Send directive to peasant |
| `kd peasant read <id>` | Read messages from peasant |
| `kd peasant review <id>` | Review peasant's completed work |

### Other

| Command | Description |
|---------|-------------|
| `kd work <id>` | Run autonomous agent loop on a ticket |

## Council Guidelines

- **When to consult**: major architectural decisions, technology choices with trade-offs, design patterns that could go multiple ways, when uncertain about an approach.
- **When not to**: straightforward implementation, bug fixes with obvious solutions, tasks the King has already decided on.
- **Do not synthesize**: council responses are saved to `.kd/branches/<branch>/threads/`. Point the King to the thread and let them read directly. The King decides — you execute.
- **Commit `.kd/` changes** as you go (ticket moves, closures, threads).

## Deep Dives

- [Council patterns and usage](references/council.md)
- [Ticket lifecycle and management](references/tickets.md)
- [Peasant workers and worktrees](references/peasants.md)
