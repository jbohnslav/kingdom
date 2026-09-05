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

Use `uv run kd` only when the current repository is Kingdom's own source
checkout, so every command exercises working-tree code. In every other
repository—including Python/uv projects—use the installed `kd` command directly.

## The Core Loop — Run When Resolving or Changing Context

The reflex is not "always create." It is: **make sure the request is represented
exactly once, then keep that ticket current.**

### 1. Resolve context and search first

Run the context-discovery commands once when beginning a new request, after
changing branches, or when ticket ownership may have changed. Do not repeat
them for routine follow-ups on an already-resolved ticket. Reuse known context
during ongoing work and keep its ticket current.

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

When a ticket has dependencies, use the resolved statuses and dependency gate
shown by `kd tk show <id>`. A dependency edge alone is not a blocker: report a
ticket as blocked only when its gate identifies a dependency whose status is not
`closed`.

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

Use the inline form only for a short plain-text-only note without shell
metacharacters:

```bash
kd tk log <id> "short plain text note"
```

For command-rich or multiline notes, use stdin with a quoted delimiter so the
shell cannot expand backticks, `$()`, variables, or quotes:

```bash
kd tk log <id> <<'WORKLOG'
Verified `uv run pytest`; literal $HOME and $(pwd) were not expanded.
Record the second line here.
WORKLOG
```

Alternatively, edit the ticket as direct Markdown for rich updates. Find the
canonical file with `kd tk find <id>` or the `File:` line from
`kd tk show <id>`.

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
- Do not infer that a ticket is blocked merely because it has dependencies;
  inspect their resolved statuses and treat only non-closed dependencies as
  blockers.
- Do not swallow failed `kd` commands. Diagnose them and preserve blockers in the
  ticket.
- Commit `.kd/` state and worklogs alongside the code they explain.
- Run `kd status --check` before creating or merging the PR; it validates
  workspace readiness without mutating state.

## Common Routing Decisions

- Existing selected work is no longer for now → `kd tk defer <id> --reason "..."`.
- Backlog work is selected now → `kd tk pull <id>...`.
- Relocate a branch, backlog, or archived ticket →
  `kd tk move <id> --to-branch <branch>` preserves status and all ticket contents,
  including closed evidence. The destination board must already exist.
- Stale execution-context bindings → `kd status --prune-stale`.
- Retained or stale peasant resources → `kd peasant clean <id>` or
  `kd peasant prune`; accepted workers are cleaned by `kd peasant accept`.
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
kd status --check
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
kd status --check
```

Design documents, council, and autonomous workers are optional. Context resolution,
accurate tickets, durable updates, and verified state transitions are not.

For repositories upgrading to 1.0, replace `kd done` with the read-only
`kd status --check` readiness gate and replace `kd switch <branch>` with the
idempotent `kd start <branch>`. Ticket closure clears that ticket's active
bindings; stale contexts and peasant resources remain owned by the cleanup
commands above, so no global finalizer is needed.

## Command Quick Reference

```bash
kd start / status / status --check / status --prune-stale
kd tk current / list / show / find
kd tk list --recently-closed --limit 10
kd tk create / start / log / close / reopen
kd tk pull / defer / move / deps / link / unlink
kd peasant start / status / watch / review / accept / reject / clean / prune
kd lord start / status / watch / stop
kd council ask / show / list / watch / retry
```

Run `kd <command> --help` for exact flags.

## References

- [Ticket lifecycle, direct editing, examples, and recovery](references/tickets.md)
- [Peasant execution, council review, and merge recovery](references/peasants.md)
- [Council selection, threading, and follow-through](references/council.md)
