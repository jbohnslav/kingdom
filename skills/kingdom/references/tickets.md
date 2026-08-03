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
kd tk list --recently-closed # show closed tickets ordered by most recent close
kd tk list --recent --limit 10  # short alias plus result limit
kd tk show <id>              # print raw ticket Markdown (LLM-friendly)
kd tk show <id> --rich       # show framed human-friendly ticket details
kd tk defer <id>... --reason "..."  # return selected work to backlog
kd tk pull <id>...                  # select backlog work for current branch
```

## Backlog

The backlog at `.kd/backlog/tickets/` holds work that is not planned now. Use `kd tk create --backlog` to add new work, `kd tk pull <id>...` to select it for the current branch, and `kd tk defer <id>... --reason "..."` to return selected work with lifecycle history. `kd tk move` is deprecated and will be removed in v1.0.0; migrate branch-to-branch use to defer, switch/check out the target branch, then pull.

## Best Practices

- **Commit `.kd/` changes as you go** — ticket state changes, closures, pulls, and deferrals are tracked in git
- **Use dependencies** to enforce ordering when tickets have prerequisites
- **Edit ticket Markdown directly** for body text, acceptance criteria, scope changes, and multi-line worklog entries
- **Use `kd tk log` only for short one-off worklog notes**; do not contort ticket content edits through CLI commands
- **Append a work log** to the ticket body when closing — record key decisions and what was done
- **Use `kd tk list --ready`** to find the next unblocked ticket rather than picking arbitrarily
- **Use `kd tk list --recently-closed --limit 10`** when reviewing recently completed work
