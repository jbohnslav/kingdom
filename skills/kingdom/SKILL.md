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

You assist the developer (the "King") using the `kd` CLI. There are two common workflows — pick the one that fits.

**Safety rule:** Only run state-modifying `kd` commands when the King explicitly asks. Read-only commands (`kd status`, `kd tk list`, `kd tk show`, `kd design show`) are always safe.

## Workflow A: New Feature (design-first)

```
git checkout -b <branch>
kd start                        # init branch
kd design show                  # view/iterate on design doc
# iterate with council, co-author the design with the King
kd design approve
# create tickets from the design (via skill or manually with kd tk create)
# execute tickets (see below)
kd done                         # archive branch before merging PR
```

The design phase is collaborative: the King drives direction, you draft content, the council reviews. Use `kd council ask` to get multi-model feedback during design.

## Workflow B: Backlog Sprint (execution-first)

```
git checkout -b <branch>
kd start
kd tk pull <id> <id> ...        # pull existing backlog tickets in
# execute tickets (see below)
kd done
```

No design phase — tickets are already scoped. If a ticket is ambiguous, escalate to the King or ask the council. Don't guess.

## Executing Tickets

After either workflow produces tickets, the King (or the coding agent they're working with, sometimes called the "Hand") chooses how to work through them:

**Option A: Work tickets directly.** The King and their coding agent work tickets one at a time, following the Working Tickets guidelines below.

**Option B: Spin up peasants.** `kd peasant start <id>` spawns a background worker in its own worktree. Each peasant works one ticket at a time — the council reviews automatically, the peasant iterates until approved. Spin up multiple peasants for parallel throughput. The King monitors with `kd peasant status` and `kd peasant watch <id>`. See [peasant reference](references/peasants.md) for details.

Use A when the King wants to be hands-on. Use B for throughput on well-scoped tickets. Both can be mixed — the King might work one tricky ticket directly while peasants handle the straightforward ones.

## Working Tickets

This applies regardless of execution mode.

- **One at a time per worker**: `kd tk start <id>` → do the work → `kd tk close <id>` → commit → next ticket.
- **Worklog**: append progress notes to the ticket's `## Worklog` section as you go. Log what you're doing, what you found, commands and results, decisions and why. The King reads these to stay informed — don't make them ask.
- **Acceptance criteria**: only close a ticket when all acceptance criteria are met and the full test suite is green.
- **Decisions**: ask the King or consult the council (`kd council ask "..."`) for difficult design decisions — don't guess. Never silently resolve ambiguity on architectural, product, or UX tradeoffs.
- **For bugs: test BEFORE you fix!** Write a test that fails in the current state, fix it, then verify.
- **Bugs from this branch**: immediately write a failing test that reproduces it, then fix.
- **Bugs from elsewhere**: if not blocking, create a backlog ticket (`kd tk create --backlog "..."`) and move on.
- **Commit often**: commit code changes as you go. Commit `.kd/` changes (ticket state, worklogs) alongside code.
- **One-off tests**: write a script or temp file to test an end-to-end flow with real data. Then consider if it can be an automated integration test.
- **Dogfooding**: notice a UX issue with `kd` itself? File a backlog ticket immediately (`kd tk create --backlog "..."`).

## Council

- `kd council ask "prompt"` queries all members for independent perspectives.
- Use it proactively at decision points, not just when stuck.
- Present each member's perspective distinctly — don't flatten disagreements. Summarize if the King asks, but preserve the tensions.
- See [council reference](references/council.md) for threading, async flags, and session management.

## Command Quick-Ref

```bash
kd start / status / done              # branch lifecycle
kd design show / design approve       # design doc
kd tk list / show / list --ready      # inspect tickets
kd tk start <id> / close <id>         # work a ticket
kd tk create "title"                  # new ticket (--backlog for backlog)
kd tk pull <id>...                    # pull from backlog
kd tk deps add/remove/tree/cycle      # manage dependencies
kd council ask "prompt"               # consult council
kd council chat                       # council chat TUI
kd peasant start <id>                 # launch background worker
kd peasant status / watch <id>        # monitor peasants
kd peasant review / accept / reject   # review cycle
kd peasant msg / read                 # communicate with peasants
```

Run `kd <command> --help` for flags and options not listed here.

## References

- [Council patterns and usage](references/council.md)
- [Ticket lifecycle and management](references/tickets.md)
- [Peasant workers and worktrees](references/peasants.md)
