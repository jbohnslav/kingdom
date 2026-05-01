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

Types: `task`, `bug`, `feature`. Priorities: 0 (highest) to 3.

`-t` also works as a short title flag when no positional title is provided:
`kd tk create -t "Flag title"`. To avoid ambiguity, prefer `--title` for flag
titles and `--type` for ticket types in new examples. The legacy form
`kd tk create "Title" -t bug` remains supported.

## Working Tickets

```bash
kd tk list --ready       # show unblocked tickets
kd tk start <id>         # mark in_progress
# ... do the work ...
kd tk close <id>         # mark closed
kd tk reopen <id>        # reopen if needed
```

## Dependencies

Tickets can depend on other tickets. A ticket with unresolved dependencies won't show in `kd tk list --ready`.

```bash
kd tk deps add <id> <dep-id>      # id depends on dep-id
kd tk deps remove <id> <dep-id>   # remove dependency
kd tk deps tree <id>               # show dependency tree
kd tk deps cycle                   # detect dependency cycles
```

## Assignment

```bash
kd tk assign <id> <agent>    # assign to an agent (e.g., claude)
kd tk unassign <id>          # clear assignment
```

## Organization

```bash
kd tk list                   # list all tickets on current branch
kd tk show <id>              # print raw ticket Markdown (LLM-friendly)
kd tk show <id> --rich       # show framed human-friendly ticket details
kd tk move <id> --to <branch|backlog>  # move to another branch or backlog
kd tk pull <id>...            # pull backlog tickets into current branch
```

## Backlog

The backlog at `.kd/backlog/tickets/` holds tickets not assigned to any branch. Use `kd tk create --backlog` to add to it, and `kd tk pull <id>...` to bring tickets into the current branch.

## Best Practices

- **Commit `.kd/` changes as you go** — ticket state changes, closures, and moves are tracked in git
- **Use dependencies** to enforce ordering when tickets have prerequisites
- **Append a work log** to the ticket body when closing — record key decisions and what was done
- **Prefer direct Markdown edits** when agents need to update ticket body, acceptance criteria, and worklog repeatedly in one turn
- **Use `kd tk list --ready`** to find the next unblocked ticket rather than picking arbitrarily
