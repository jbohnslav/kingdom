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

All `kd` commands are safe to run. Use them proactively — don't wait to be told.

## Ticket-First Reflex

Every time the King says something, your first thought should be: **does this need a ticket?**

Bug report, feature idea, UX complaint, missing behavior, scope change — if there's work to be done, capture it in a ticket *immediately*. Don't start exploring, don't start coding, don't ask follow-up questions about the implementation. Get the ticket created first, then proceed. The ticket is how work gets tracked, prioritized, and not forgotten.

This applies even mid-conversation. If the King mentions a problem in passing while you're working on something else, create a backlog ticket on the spot (`kd tk create --backlog "..."`). If it's the main thing they're asking about, create it and start working it. Either way: ticket first, always.

The only exception is when you genuinely don't have enough information to write a meaningful title and description — then ask clarifying questions, but only the minimum needed to create the ticket.

## When to Reach for `kd`

Recognize these cues in conversation and translate them into the right `kd` action.

**King reports a bug with clear details.** Extract the actual vs expected behavior and open a ticket:

```
kd tk create -t bug -d "web app shows raw HTML, expected rendered markdown" "Markdown rendering broken in preview pane"
```

Only include flags the King actually provided — don't invent a priority or tags if they weren't mentioned.

**King describes a problem vaguely.** "Hey, something's wrong with the backend" is not enough to create a ticket. Ask clarifying questions first:

- What's happening? (actual behavior)
- What should happen? (expected behavior)
- Where? (which page, endpoint, flow)
- Can you reproduce it?

Then structure the answers into a ticket:

```
kd tk create -t bug -d "Login endpoint returns 500 when email has a plus sign. Expected: normal login. Repro: try user+test@example.com" "Login fails for plus-sign emails"
```

**King wants to track an idea for later.** Suggest a backlog ticket:

```
kd tk create --backlog "Add dark mode support"
```

**King says work is done.** Close the ticket (after verifying acceptance criteria are met and tests pass):

```
kd tk close ab12
```

**King is stuck on a design choice.** Suggest consulting the council:

```
kd council ask "Should we use WebSockets or SSE for real-time updates? We need low latency but also need to work behind corporate proxies."
```

**King says "ask the council."** Every `kd council ask` creates a new thread by default. If the conversation is a continuation of an active design discussion, use `kd council ask --continue "follow-up question"` to append to the current thread. When ambiguous, check existing threads with `kd council list` or `kd council show <thread>`, or ask the King a brief clarifying question before running the command.

**King wants to note progress.** Log it against the active ticket:

```
kd tk log ab12 "Finished the API refactor, all endpoint tests passing"
```

**King wants parallel execution.** Start a peasant worker:

```
kd peasant start ab12
```

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

## Automatic Worklog Updates

Proactively `kd tk log` whenever a durable state change occurs. The King should never have to say "update the worklog." Log against the active ticket without asking which ticket — you know what you're working on.

The threshold is **durable state change**, not every chat turn. If future-you or another agent would need this fact, log it now.

**Log before you continue.** When you discover durable information — a relevant issue, a root cause, a key finding from research — run `kd tk log` immediately, before continuing your work. The worklog survives context compaction; chat doesn't. Don't let valuable findings exist only in conversation history that will be compressed away.

**Edit ticket body vs worklog.** If the King changes requirements or acceptance criteria, update the ticket's markdown directly (description, AC section). The worklog is for timeline events — decisions, findings, progress, blockers. Don't stuff requirements into `kd tk log`; edit the ticket file instead.

**Decision made** — King says "let's go with raw TypeScript over React":

```
kd tk log ab12 "Decision: raw TypeScript, not React — King's call

Rationale: we want full control over the build pipeline without
React's abstraction layer. This means we'll need to handle routing
and state management ourselves, but the bundle size stays minimal
and we avoid the React upgrade treadmill.

Affected tickets: may need to revisit ab34 (component library choice)"
```

**Root cause discovered** — you trace a bug to an unexpected place:

```
kd tk log ab12 "Root cause: stale cache in render_template()

The DB query was a red herring — render_template() caches the compiled
template and never invalidates when the schema changes. Found by tracing
the actual SQL output, which was correct. The fix is to add a cache key
that includes the schema version.

Affected files: src/kingdom/render.py, src/kingdom/cache.py"
```

**Scope change** — work expands or shifts mid-ticket:

```
kd tk log ab12 "Scope change: also need to update the migration script

The original ticket only covered the model changes, but the migration
script hardcodes the old column names. Without updating it, existing
installs will break on upgrade. Adding migration updates to this ticket
rather than splitting — it's the same logical change."
```

**Blocker cleared** — something that was stuck is now unblocked:

```
kd tk log ab12 "Unblocked: upstream API now returns correct schema

Tested against staging at 14:30 — the v2 endpoint returns the
'metadata' field we need. Removing the workaround shim and switching
to direct parsing. This also unblocks ticket cd56 (metadata display)."
```

Rich, multi-line log entries are encouraged — a worklog entry is a place to dump everything you know in the moment, not a tweet.

## Workflow Reflexes

Decision patterns to get right:

- **Default to the active ticket.** If you're working a ticket, that's the target for `kd tk log`, `kd tk close`, and status updates. Don't ask "which ticket?" when context is obvious.
- **Move vs create.** "This work belongs somewhere else" → `kd tk move ab12 --to backlog`. "This is a separate problem I just noticed" → `kd tk create --backlog "..."`. Log is for new information about the current work; create/move is for separate work.
- **Council follow-through.** After `kd council ask`, summarize the key perspectives and disagreements for the King, log the decision that came out of it (`kd tk log`), and move on. Don't dump the raw council response and wait for the King to synthesize.
- **Close-out hygiene.** Before `kd tk close`: update the worklog with what changed and how it was verified, confirm tests pass. Closing is the last step after evidence is captured, not a declaration of intent.

## When `kd` Says No

When a command fails, diagnose before retrying. Never silently drop a failed operation.

- **`kd tk close` fails — deps not met.** Inspect with `kd tk deps tree <id>`, figure out what's blocking, work the blocker or tell the King.
- **No obvious active ticket.** Run `kd tk current` to check. Don't guess.
- **`kd council ask` times out or errors.** Run `kd council retry` to re-query failed members. Don't re-run the same ask from scratch.
- **`kd peasant start` fails — ticket is in_review or closed.** The ticket needs to be reopened or the review resolved before a peasant can work it. Check ticket status with `kd tk show <id>` and tell the King.
- **Peasant seems stuck.** Check `kd peasant status` and `kd peasant show <id>` before escalating to the King.
- **Council query sent — want to check on it.** Run `kd council show` to read the thread and see which members have responded. Don't re-run `kd council ask` with the same prompt.
- **`kd peasant accept` fails — merge conflicts.** See "Merge Conflict Recovery" below.

## Merge Conflict Recovery

When `kd peasant accept <id>` hits merge conflicts, the merge happens on the **feature branch** (not in the worktree). The command leaves you in a merge state with conflict markers in your working tree.

**Before accepting:** Commit or stash any uncommitted changes on the feature branch first. Accept will refuse to merge if the working tree is dirty.

**Recovery steps when conflicts occur:**

1. You are already on the feature branch with conflict markers in the working tree.
2. Resolve the conflict markers in each file (combine both sides as needed).
3. `git add <resolved files> && git commit` — this completes the merge.
4. `kd peasant accept <id>` — re-run accept. It detects the branch is already merged and proceeds with cleanup (close ticket, update session).

Accept is idempotent: if the ticket branch is already merged into the feature branch, it skips the merge step and goes straight to cleanup. This means you can safely re-run accept after manual conflict resolution.

## Council

- `kd council ask "prompt"` queries all members for independent perspectives.
- Use it proactively at decision points, not just when stuck.
- Present each member's perspective distinctly — don't flatten disagreements. Summarize the key perspectives and disagreements for the King, and preserve the tensions. Link or reference the thread for full detail.
- See [council reference](references/council.md) for threading, async flags, and session management.

## Command Quick-Ref

```bash
kd start / status / done                                # branch lifecycle
kd design show / design approve                         # design doc
kd tk list / show / list --ready                        # inspect tickets
kd tk start <id> / close <id>                           # work a ticket
kd tk current                                           # show active ticket
kd tk pull <id>...                                      # pull from backlog
kd tk log <id> "message"                                # append to worklog
kd tk deps add/remove/tree/cycle                        # manage dependencies
kd peasant status / watch <id>                          # monitor peasants
kd peasant review / accept / reject                     # review cycle
kd peasant msg / read                                   # communicate with peasants

# ticket creation — use only the flags the King provides
kd tk create "title"                                    # minimal
kd tk create -t bug -d "details" "title"                # bug with description
kd tk create -t bug -p 2 -d "details" "title"           # with priority (only if King specified it)
kd tk create --backlog "title"                           # backlog ticket
kd tk create --backlog --ac "criterion" "title"          # backlog with acceptance criteria

# council — threading and targeting
kd council ask "prompt"                                  # all members, new thread
kd council ask --continue "prompt"                       # continue current thread
kd council ask --to claude "prompt"                      # single member
kd council list / show <thread>                          # inspect threads
kd council retry                                         # re-query failed members

# peasants — launch modes
kd peasant start <id>                                    # worktree (parallel)
kd peasant start <id> --hand                             # serial in cwd
```

Run `kd <command> --help` for flags and options not listed here.

## References

- [Council patterns and usage](references/council.md)
- [Ticket lifecycle and management](references/tickets.md)
- [Peasant workers and worktrees](references/peasants.md)
