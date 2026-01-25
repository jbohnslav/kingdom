# Kingdom MVP Plan

This MVP delivers the minimum useful workflow: talk to the Hand, plan with the Council, and hand off work to a Peasant. It deliberately avoids full auto-review or merge-queue behavior while establishing the framework for later expansion.

## Scope

- Persistent Hand chat via `kd chat`
- Council-backed planning via `kd plan` using `claude`, `codex`, and `agent`
- Ticket creation via `tk` (markdown tickets only)
- Single Peasant handoff via `kd peasant <ticket>`
- `kd dev` reserved to start the broader develop phase later (MVP can delegate to `kd peasant`)

Not in scope:
- Parallelized Peasants
- Auto-review / auto-merge queue
- `plan.json` or other non-markdown plan artifacts

## Workflow

1. `kd start <feature>` initializes state, branches, and tmux session.
2. `kd chat` starts the Hand in a persistent window.
3. `kd plan` runs Council to draft a ticket plan into `plan.md`.
4. Hand iterates in-place with the user until the plan is approved.
5. Hand offers to apply the plan, creating `tk` tickets.
6. `kd peasant <ticket>` starts a Peasant to execute a ticket.

## Plan File Format

`plan.md` is the single source of truth for the planning phase. It is updated in-place while planning is active. If the plan changes after work begins, new changes are appended under a revision section.

Suggested format:

```markdown
# Plan: <feature>

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

The Hand converts `plan.md` tickets into `tk` commands and asks for approval before applying. Mapping:

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
        ├── plan.md
        └── logs/
            ├── hand.jsonl
            └── council.jsonl
```

## Commands

- `kd start <feature>`: initialize run, tmux server/session, and state
- `kd chat`: talk to the Hand
- `kd council`: open council panes (claude/codex/agent + synthesis)
- `kd plan`: run/iterate the plan and update `plan.md`
- `kd peasant <ticket>`: start a Peasant in a worktree for a ticket
- `kd dev`: start the broader develop phase later (MVP may delegate to `kd peasant`)
- `kd status`: show current phase and tickets
- `kd attach <target>`: attach to `hand`, `council`, or `peasant-1`

## Notes

- Plan edits are in-place until dev starts. After dev starts, plan changes append to `## Revisions`.
- Tickets are always markdown via `tk` in `.tickets/`.
- This MVP is intentionally minimal; review/merge automation can be layered on later.
