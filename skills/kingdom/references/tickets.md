# Ticket Lifecycle and Management

Tickets track units of work within a branch. They live in `.kd/branches/<branch>/tickets/<id>.md` as markdown files with YAML frontmatter.

## Ticket States

```
open → in_progress → closed
                  ↗
         (reopen)
```

- **open** — created, not yet started
- **in_progress** — actively being worked on
- **closed** — completed

## Creating Tickets

```bash
kd tk create "Fix login validation"                    # default: P2, task type
kd tk create -p 1 -t bug "Critical auth failure"       # P1 bug
kd tk create -t feature -d "Description here" "Title"  # with description
kd tk create --backlog "Future improvement"             # create in backlog, not current branch
```

Types: `task`, `bug`, `feature`. Priorities: 1 (highest) to 3.

## Working Tickets

```bash
kd tk ready              # show unblocked tickets
kd tk start <id>         # mark in_progress
# ... do the work ...
kd tk close <id>         # mark closed
kd tk reopen <id>        # reopen if needed
```

## Dependencies

Tickets can depend on other tickets. A ticket with unresolved dependencies won't show in `kd tk ready`.

```bash
kd tk dep <id> <dep-id>      # id depends on dep-id
kd tk undep <id> <dep-id>    # remove dependency
```

## Assignment

```bash
kd tk assign <id> <agent>    # assign to an agent (e.g., claude)
kd tk unassign <id>          # clear assignment
```

## Organization

```bash
kd tk list                   # list all tickets on current branch
kd tk show <id>              # show ticket details
kd tk edit <id>              # open in $EDITOR
kd tk move <id> <branch>     # move to another branch
kd tk pull                   # pull backlog tickets into current branch
```

## Backlog

The backlog at `.kd/backlog/tickets/` holds tickets not assigned to any branch. Use `kd tk create --backlog` to add to it, and `kd tk pull` to bring tickets into the current branch.

## Best Practices

- **Commit `.kd/` changes as you go** — ticket state changes, closures, and moves are tracked in git
- **Use dependencies** to enforce ordering when tickets have prerequisites
- **Append a work log** to the ticket body when closing — record key decisions and what was done
- **Use `kd tk ready`** to find the next unblocked ticket rather than picking arbitrarily
