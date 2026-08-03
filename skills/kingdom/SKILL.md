---
name: kingdom
description: >
  Ticket-first multi-agent development workflow using the kd CLI. Resolves
  existing context, tracks epics and tickets, preserves durable worklogs, and
  selects direct work, native subagents, reviewed peasant workers, lords, or
  council consultation deliberately. Use when capturing or updating development
  work, starting a feature branch, delegating execution, or consulting multiple
  models. Requires the kd CLI to be installed and on PATH.
compatibility: Requires Python 3.11+, kd CLI (uv tool install kingdom-cli), git
---

You assist the developer (the "King") using the `kd` CLI. Use `kd` proactively;
the ticket is the durable record of what the team is doing and why.

## Developing Kingdom Itself

Inside a Kingdom source checkout, invoke every command shown below as
`uv run kd ...`. This is the canonical dogfood invocation and guarantees the
command exercises working-tree code. Bare `kd ...` remains correct for normal
installed-user projects, but may resolve to a stale installed release while
developing Kingdom.

## The Core Loop — Follow It Every Turn

The reflex is not "always create." It is: **make sure the request is represented
exactly once, then keep that ticket current.**

### 1. Resolve context and search first

Before creating work, take a fast read-only pass:

```bash
kd status
kd tk current
kd tk list
kd tk list --recently-closed --limit 10
```

Search active, backlog, archived, parent, and related ticket titles/content with
`kd tk show <id>` and the host's file-search tools. This is context discovery,
not implementation exploration. Stop as soon as you can answer:

- Which branch, epic, and ticket owns this request?
- Is the request already represented by active or recent work?
- Is it a scope change to that work, or a genuinely separate unit?

Do not create a duplicate umbrella ticket because the current session or epic
was overlooked.

### 2. Update existing work or create a small ticket

- **Existing request:** use the existing ticket. Update its requirements,
  acceptance criteria, links, or worklog immediately.
- **Genuinely new primary request:** create a small, concrete ticket immediately,
  before broad exploration or implementation, then start it.
- **Separate issue noticed in passing:** capture it in the backlog and continue
  the current ticket.
- **Too vague to title meaningfully:** ask only the minimum questions needed to
  represent the work accurately.

```bash
kd tk create "Short concrete title"
kd tk start <id>
kd tk create --backlog "Separate issue for later"
```

Use only priority, type, and tags the King actually supplied. Do not invent
metadata. See [ticket lifecycle and management](references/tickets.md) for
creation variants, search patterns, and lifecycle commands.

### 3. Choose the execution level deliberately

Choose the lightest level that gives the work enough isolation and review:

- **Direct work:** small, tightly coupled, sequential work where the owning
  session should implement and verify the ticket itself.
- **Native subagent:** the default for bounded host-local delegation—focused
  research, review, or an independent implementation slice. The owning session
  retains the ticket and must review and merge the child's findings, changes,
  evidence, and remaining concerns into the durable ticket.
- **Reviewed peasant:** unattended implementation of a well-scoped ticket in an
  isolated worktree. `kd peasant start <id>` keeps peasant-to-council review as
  the default; do not bypass that review merely for speed. Use peasants when
  durable autonomous iteration is more valuable than host-local coordination.
- **Lord:** epic-level supervision when several ready tickets should be scheduled,
  reviewed, and integrated through peasants: `kd lord start <epic-id>`.
- **Council:** independent perspectives for real ambiguity, architecture,
  product tradeoffs, or review blind spots. It advises; it does not replace the
  ticket owner or execution worker.

These levels can be mixed. For example, the owning session can implement one
integration-sensitive ticket directly, delegate a bounded audit to native
subagents, and run reviewed peasants on independent tickets.

See [peasant workers and worktrees](references/peasants.md) and
[council patterns](references/council.md) for the detailed workflows.

### 4. Keep the ticket alive while work happens

The ticket is a living Markdown document, not a receipt written at the end.
Whenever something durable changes, update it **before continuing**:

- New fact, root cause, decision, result, command evidence, or blocker → append
  it to `## Worklog`.
- Requirement, scope, acceptance criterion, dependency, or relationship changes
  → edit the relevant ticket body/frontmatter or use the matching lifecycle
  command.
- Acceptance criterion is satisfied → check it off.
- Work starts, moves, defers, reviews, closes, or reopens → update lifecycle state
  with `kd`.
- Native subagent returns → the owning session synthesizes its useful output into
  the ticket. A chat response or automatic child handoff alone is not durable
  integration.

Edit the ticket Markdown directly for rich or multi-line updates. Use
`kd tk log <id> "short note"` only for a quick one-off entry. Find the canonical
file with `kd tk find <id>` or the `File:` line from `kd tk show <id>`.

The threshold is durable state, not conversational noise: if a future session,
reviewer, or worker would need it, write it down now.

### 5. Verify, record, then transition

Before declaring work complete:

1. Review delegated results and integrate them into the working tree and ticket.
2. Run verification proportional to the change; for code tickets, the full test
   suite must pass.
3. Record changed files, commands, results, decisions, and remaining concerns in
   the worklog.
4. Check acceptance criteria and update ticket relationships/state.
5. Close the ticket only after the evidence is durable, then commit the ticket
   state with the implementation.

## Non-Negotiable Working Rules

- One active ticket per worker: start → work → verify → close → commit.
- For bugs, write and run a failing regression test before the fix.
- Do not silently decide architectural, product, or UX ambiguity; ask the King or
  consult the council, then record the decision.
- Do not swallow failed `kd` commands. Diagnose them and preserve blockers in the
  ticket.
- Commit `.kd/` state and worklogs alongside the code they explain.
- Run `kd done` before creating or merging the PR; it verifies branch completion.

## Common Routing Decisions

- Existing selected work is no longer for now → `kd tk defer <id> --reason "..."`.
- Backlog work is selected now → `kd tk pull <id>...`.
- Branch-to-branch work → defer it, switch/check out the target, then pull it.
- Council follow-up on the same decision → `kd council ask --continue "..."`.
- A peasant completes → inspect `kd peasant review <id>` and council feedback,
  then accept or reject; council approval does not remove owning-session review.
- A native subagent completes → review its output and merge the durable parts
  into the ticket yourself.
- A command fails or state diverges → use the recovery section in the relevant
  reference instead of retrying blindly.

## Workflow Entry Points

New feature (ticket-first default):

```bash
git checkout -b <branch>
kd start
kd tk create --type epic "Concrete feature outcome"
kd tk create --parent <epic-id> "First executable slice"
# start directly or delegate each ready child deliberately
kd done
```

Optional planning when real ambiguity or cross-cutting design warrants it:

```bash
kd design show
kd council ask "Review the unresolved tradeoffs in this feature"
kd design approve
# merge approved decisions and scope into the epic and child tickets
```

Backlog sprint:

```bash
git checkout -b <branch>
kd start
kd tk pull <id> <id> ...
# execute and close tickets one at a time per worker
kd done
```

Design documents, council, and autonomous workers are optional. Context resolution,
accurate tickets, durable updates, and verified state transitions are not.

## Command Quick Reference

```bash
kd status / start / done
kd tk current / list / show / find
kd tk list --recently-closed --limit 10
kd tk create / start / log / close / reopen
kd tk pull / defer / deps / link / unlink
kd peasant start / status / watch / review / accept / reject
kd lord start / status / watch / stop
kd council ask / show / list / watch / retry
```

Run `kd <command> --help` for exact flags.

## References

- [Ticket lifecycle, direct editing, examples, and recovery](references/tickets.md)
- [Peasant execution, council review, and merge recovery](references/peasants.md)
- [Council selection, threading, and follow-through](references/council.md)
