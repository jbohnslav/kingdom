# Kingdom MVP

This MVP delivers the minimum useful workflow: talk to the Hand, draft a design doc, break it down into tickets, and hand off work to a Peasant. It deliberately avoids full auto-review or merge-queue behavior while establishing the framework for later expansion.

## Scope

- Persistent Hand chat via `kd chat`
- Council-backed design via `kd chat` + `/design` using `claude`, `codex`, and `agent`
- Council-backed breakdown via `kd chat` + `/breakdown` using `claude`, `codex`, and `agent`
- Ticket creation via `tk` (markdown tickets only)
- Single Peasant handoff via `kd peasant <ticket>`
- `kd dev` reserved to start the broader develop phase later (MVP can delegate to `kd peasant`)

Not in scope:
- Parallelized Peasants
- Auto-review / auto-merge queue
- Any non-markdown artifacts (e.g., JSON plan formats)

## Workflow

1. `kd start <feature>` initializes state, branches, and tmux session.
2. `kd chat` starts the Hand in a persistent window.
3. `kd design` initializes `design.md` (template).
4. In `kd chat`, use `/design` to iterate on `design.md` with Council input until approved.
5. `kd breakdown` initializes `breakdown.md` (template).
6. In `kd chat`, use `/breakdown` to iterate on `breakdown.md` with Council input until approved.
7. `kd breakdown --apply` creates `tk` tickets from `breakdown.md`.
8. `kd peasant <ticket>` starts a Peasant to execute a ticket.

## Design File Format

`design.md` is the single source of truth for intent/decisions during the Design phase. It is updated in-place while designing is active.

Suggested format:

```markdown
# Design: <feature>

## Goal
<what outcome are we trying to achieve?>

## Context
<what exists today / why this matters>

## Requirements
- <requirement>

## Non-Goals
- <explicitly out of scope>

## Decisions
- <decision>: <rationale>

## Open Questions
- <question>
```

## Breakdown File Format

`breakdown.md` is the single source of truth for the Breakdown phase: tickets, dependencies, and acceptance criteria derived from `design.md`. It is updated in-place while breakdown is active. If the breakdown changes after work begins, new changes are appended under a revision section.

Suggested format:

```markdown
# Breakdown: <feature>

## Design Summary
<1-3 sentences or a link to design.md>

## Goal
<short goal>

## Tickets
- [ ] T1: <title>
  - Priority: 2
  - Depends on: <none|ticket ids>
  - Description: ...
  - Acceptance:
    - [ ] ...

## Revisions
(append-only after dev starts)
```

## Ticket Creation

The Hand converts `breakdown.md` tickets into `tk` commands and asks for approval before applying. Mapping:

- Title -> `tk create "Title"`
- Description -> `-d "..."`
- Acceptance -> `--acceptance "..."`
- Priority -> `-p 0-4`
- Dependencies -> `tk dep <id> <dep-id>`

## Council Commands

Council runs three model CLIs in parallel:

- `claude`
- `codex`
- `agent`

Synthesis defaults to `claude` unless configured otherwise.

## State Layout

```
.kd/
├── current
├── config.json
└── runs/
    └── <feature>/
        ├── state.json
        ├── design.md
        ├── breakdown.md
        └── logs/
            ├── hand.jsonl
            └── council.jsonl
```

## Commands

- `kd start <feature>`: initialize run, tmux server/session, and state
- `kd chat`: talk to the Hand
- `kd council`: open council panes (claude/codex/agent + synthesis)
- `kd design`: create `design.md` template (Design phase artifact)
- `kd breakdown`: create `breakdown.md` template (Breakdown phase artifact)
- `kd peasant <ticket>`: start a Peasant in a worktree for a ticket
- `kd dev`: start the broader develop phase later (MVP may delegate to `kd peasant`)
- `kd status`: show current phase and tickets
- `kd attach <target>`: attach to `hand`, `council`, or `peasant-1`

## Notes

- Design edits are in-place until dev starts.
- Breakdown edits are in-place until dev starts. After dev starts, breakdown changes append to `## Revisions`.
- Tickets are always markdown via `tk` in `.tickets/`.
- This MVP is intentionally minimal; review/merge automation can be layered on later.
