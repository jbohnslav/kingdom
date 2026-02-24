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

**Safety rule:** Only run state-modifying `kd` commands when the King explicitly asks. Read-only commands (`kd status`, `kd tk list`, `kd tk show`, `kd design show`) are always safe.

## Feature Lifecycle

```
git checkout -b <branch>
kd start                        # init branch session
kd design                       # create design doc template
# ... write design, consult council ...
kd design approve
kd breakdown                    # get prompt for creating tickets
# ... create tickets, work them, close them ...
kd done                         # archive branch (run before merging PR)
```

Check status anytime: `kd status`

## Everyday Commands

```bash
# Tickets
kd tk list / show <id> / ready          # see what's available
kd tk start <id> / close <id>           # work a ticket
kd tk create "title"                    # create (--backlog for backlog)
kd tk dep <id> <dep-id>                 # add dependency

# Council
kd council ask "prompt"                 # query all members
kd council ask --to <member> "prompt"   # query one member
kd council ask --new-thread "prompt"    # fresh thread (new topic)
kd council review                       # review current branch diff
kd council show <thread-id>             # display a thread
kd council list                         # list all threads

# Peasants
kd peasant start <id>                   # launch in worktree (parallel)
kd peasant start <id> --hand            # launch in cwd (serial)
kd peasant status / logs <id> / stop <id>
kd peasant watch <id>                   # tail worklog live
kd peasant review <id>                  # review completed work
```

Run `kd <command> --help` for flags and options not listed here.

## Working Tickets

`kd tk start <id>` → do the work → `kd tk close <id>` → commit → next ticket.

- Close only when all acceptance criteria are met and the full test suite is green.
- Append progress notes to the ticket's `## Worklog` section.
- Raise hard design decisions with the King or the council — don't guess.
- Bugs from this branch: write a failing test, then fix. Bugs from elsewhere: `kd tk create --backlog "title"` and move on.
- Commit `.kd/` changes (ticket state, worklogs, threads) alongside code.

## Council Guidelines

- **Consult** for architectural decisions, technology trade-offs, or design uncertainty.
- **Skip** for straightforward implementation, obvious bug fixes, or decided tasks.
- With `--async`, always add `--no-watch` to avoid blocking. Use `kd council watch <thread-id>` separately.
- **Don't synthesize responses.** Point the King to the thread — they decide, you execute.

## References

- [Council patterns and usage](references/council.md)
- [Ticket lifecycle and management](references/tickets.md)
- [Peasant workers and worktrees](references/peasants.md)
