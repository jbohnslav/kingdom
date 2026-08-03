# Ticket Lifecycle and Management

Tickets track units of work within a branch. They live in `.kd/branches/<branch>/tickets/<id>.md` as markdown files with YAML frontmatter.

## Resolve Context Before Creating

The goal is one accurate ticket per unit of work, not one new ticket per user
message. Before creation, identify the active execution context and scan current,
recent, backlog, archived, parent, and related work:

```bash
kd status
kd tk current
kd tk list
kd tk list --recently-closed --limit 10
kd tk show <related-id>
```

Use the host's file search across `.kd/**/tickets/*.md` when title scans are not
enough. If the request already belongs to a ticket, update that ticket. Create a
small new ticket only when the request is genuinely separate.

## Ticket States

```
open → in_progress → in_review → closed
closed → open             (reopen)
in_review → in_progress   (reject for iteration)
```

- **open** — created, not yet started
- **in_progress** — actively being worked on
- **in_review** — implementation complete and awaiting review/acceptance
- **closed** — completed

## Creating Tickets

```bash
kd tk create "Fix login validation"                         # default: P2, task type
kd tk create --priority 1 --type bug "Critical auth failure" # P1 bug
kd tk create --type feature -d "Description here" "Title"   # with description
kd tk create --backlog "Future improvement"                  # backlog, not current branch
```

Types: `task`, `bug`, `feature`, `epic`. Priorities: 0 (highest) to 3.

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
- **Edit ticket Markdown directly** for body text, acceptance criteria, scope changes, and rich worklog entries
- **Use inline `kd tk log` only for short plain-text-only notes**; send command-rich or multiline notes through stdin or direct Markdown editing so the shell cannot expand them
- **Append a work log** to the ticket body when closing — record key decisions and what was done
- **Use `kd tk list --ready`** to find the next unblocked ticket rather than picking arbitrarily
- **Use `kd tk list --recently-closed --limit 10`** when reviewing recently completed work

## Durable Ticket Updates

Use lifecycle commands for status and movement. Edit Markdown directly for the
ticket's meaning:

- requirements, scope, and acceptance criteria
- parent, dependency, and related-work context
- decisions and their rationale
- root causes and rejected leads
- verification commands and results
- blockers, handoffs, and remaining concerns

Append durable discoveries to `## Worklog` before continuing. A useful entry
states what changed, why it matters, the evidence, and any affected work. Keep
requirements in the ticket body rather than burying them in timeline notes.

The owning session must synthesize native-subagent results into these durable
sections. Automatic hook handoffs and chat responses are useful inputs, but they
do not replace ownership of the ticket's final state.

## Recovery

- No obvious active ticket: run `kd tk current`, then resolve branch and session
  context with `kd status`.
- Close fails because dependencies are unmet: inspect
  `kd tk deps tree <id>` and work or report the blocker.
- Selected work is no longer timely: use `kd tk defer <id> --reason "..."`, not a
  worklog note pretending the lifecycle did not change.
- Work belongs on another branch: defer it, switch/check out the target, then
  pull it there.
- State or content is stale: inspect the raw Markdown with `kd tk show <id>`,
  correct it explicitly, and record why.
