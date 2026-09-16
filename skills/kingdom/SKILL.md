---
name: kingdom
description: >
  Track and organize development work with the kd CLI and Markdown tickets.
  Use when capturing or updating work, starting a feature branch, delegating
  execution, or consulting the council in a Kingdom-managed project.
compatibility: Requires Python 3.11+, kd CLI (uv tool install kingdom-cli), git
---

You assist the developer (the "King") using Kingdom. Each meaningful unit of
work should be represented once, with a ticket that explains the current work
and leaves enough context for the next person or agent to continue.

## Keep the ticket true

The ticket's Markdown body is the working document: purpose, scope, acceptance
criteria, current plan, findings, and open questions. Edit it directly as your
understanding changes. Rewrite stale descriptions, consolidate findings, and
reorganize sections when that makes the work clearer. A reader should not need
to reconstruct the current task from its worklog.

Use the worklog for useful history: why an approach changed, significant rejected
leads, verification evidence, blockers, and handoffs. Append it directly or use
`kd tk log`, whichever suits the update. A log entry does not substitute for
correcting the body, and a routine turn needs no ticket operation when nothing
durable changed.

Use `kd` commands for lifecycle state, ownership, and structured relationships;
these manage validation, bindings, and history beyond the Markdown fields.
Commit ticket changes alongside the work they explain. Before handoff or
completion, leave the ticket's meaning, state, and verification evidence accurate,
following the repository's testing policy. `kd status --check` is the read-only
readiness gate before creating or merging a PR.

## Exercise judgment

Reuse the owning ticket and context already established in the conversation.
Look up only what is missing or plausibly changed; a new message is not a reason
to repeat orientation commands. Represent separate work with a new ticket;
revise existing work when its scope evolves. Capture incidental issues in the
backlog, and defer selected work that is no longer for now.

Adapt the organization to the task. A focused ticket may need only a description
and acceptance criteria; a larger effort may benefit from an epic, distinct child
tickets, a plan, or a findings section. Make routine editorial and organizational
decisions yourself. Preserve the King's intent and make substantive changes to
requested outcomes visible rather than silently redefining success.

## Choose how to execute

Use the lightest approach that provides the needed isolation and review:

- **Direct work** for small or tightly coupled tasks.
- **Native subagents** for bounded independent investigation or implementation.
  The owning agent reviews and integrates their results into the ticket.
- **Reviewed peasants** for unattended implementation in isolated worktrees.
  Council review is the default; the owning agent still reviews before acceptance.
- **Lords** for coordinating an epic's ready tickets through peasants.
- **Council** for independent perspectives on consequential ambiguity or review
  blind spots. Advice informs the owner's decision.

These approaches can be combined as the work warrants. Read the relevant
reference for mechanics, rather than treating examples as a required sequence:

- [Ticket lifecycle, Markdown edits, command examples, and recovery](references/tickets.md)
- [Peasant workers, lords, review, and worktrees](references/peasants.md)
- [Council consultation and follow-through](references/council.md)

## CLI environment

Use `uv run kd` only in Kingdom's own source checkout so commands exercise the
working tree. In other repositories, including Python/uv projects, use installed
`kd`. Use `kd <command> --help` when exact flags are needed.
