# Design: MVP Next Step — Breakdown → Tickets Polish

As of 2026-02-03, the MVP workflow is mostly implemented end-to-end, but the
Breakdown → Ticket creation step is not yet “MVP safe” (idempotent + explicit
approval) per `docs/MVP.md`.

This document captures the current state (with code pointers) and the next
concrete step to finish the MVP.

## Goal

Make `kd breakdown --apply` safe and pleasant:

- Idempotent (safe to run repeatedly without duplicating tickets)
- Explicit approval before mutating ticket state (create/dep)
- Clear output that matches `docs/MVP.md`

## Current State (Code Pointers)

### Breakdown authoring (interactive)

- Hand interactive loop and mode switching:
  - `src/kingdom/hand.py`
    - `/design`, `/design approve` switches to breakdown mode
    - `/breakdown` edits breakdown using Council + Hand prompts
- Breakdown prompt + parser utilities:
  - `src/kingdom/breakdown.py`
    - `build_breakdown_council_prompt(...)`
    - `build_breakdown_update_prompt(...)`
    - `parse_breakdown_update_response(...)`
    - `write_breakdown(...)` (atomic write)

### Ticket creation from breakdown (CLI)

- CLI entrypoint:
  - `src/kingdom/cli.py`
    - `breakdown(..., apply: bool = False)` implements `kd breakdown` and `--apply`
- Parsing breakdown tickets:
  - `src/kingdom/breakdown.py`
    - `parse_breakdown_tickets(...)`
      - Header regex matches both unchecked and checked boxes:
        `^- \\[[ xX]\\] ...` (creates risk of re-creating already “done” items)
- State storage:
  - `src/kingdom/state.py`
    - `.kd/runs/<feature>/state.json` is read/written by `read_json(...)` / `write_json(...)`
  - `src/kingdom/cli.py` writes `state["tickets"] = { ... }` mapping breakdown IDs (T1…)
    to created `tk` IDs (e.g. `nw-5c46`).

### What the docs say should happen

- `docs/MVP.md`
  - “Ticket Creation”: Hand converts `breakdown.md` tickets into `tk` commands and
    asks for approval before applying.

## Problem Statement

Today, `kd breakdown --apply`:

- Directly executes `tk create` (no dry-run / no confirmation)
- Can re-create tickets on repeated runs because ticket parsing matches `[x]`
  and there’s no “already created” skip logic

This is easy to trip over while iterating on breakdown content.

## Proposed Behavior (Minimal MVP)

### CLI UX

`kd breakdown --apply`:

1. Parse `breakdown.md` tickets intended for creation.
2. Load `state.json` and determine which breakdown IDs already have a created
   ticket ID.
3. Print a plan (the exact `tk` commands that would run).
4. Ask for confirmation:
   - Default: do nothing unless user confirms
   - Add `--yes` to skip confirmation for scripting
5. Apply:
   - Run `tk create ...` for uncreated tickets
   - Run `tk dep ...` for dependencies after creation
6. Persist updated mapping back to `state.json`.

### Idempotency Rules

- Only create tickets for unchecked breakdown items (`- [ ] ...`).
- Skip any breakdown ID already present in `state["tickets"]`.
- Dependencies:
  - If a dependency is a breakdown ID (e.g. `T1`), resolve to the created ticket
    ID if available; otherwise treat as an external ticket ID and attempt the
    dependency as-is.

### Breakdown format (keep stable)

Do not require annotating `breakdown.md` with created IDs for the MVP. The
existing `state.json` mapping is sufficient and avoids format churn.

## Acceptance Criteria

- Running `kd breakdown --apply` prints a clear plan of commands and prompts for
  confirmation before making changes.
- Re-running `kd breakdown --apply` after tickets are created:
  - Does not create duplicates
  - Re-applies no-op dependencies safely (or skips them with a clear message)
- Checked tickets (`- [x] ...`) are not created.
- Behavior matches the intent of `docs/MVP.md` “Ticket Creation”.

## Secondary Doc/Code Mismatch (Not This Step, But Next)

The docs describe `kd council` as a tmux “council window” with parallel panes.
Current implementation in `src/kingdom/cli.py` treats `kd council` as a one-shot
query and uses tmux behavior mainly via `kd attach council` (tailing log files).

If we want strict alignment to `docs/MVP.md`, the next step after ticket-creation
polish is to either:

- Implement tmux-pane council behavior for `kd council`, or
- Update docs to reflect the existing one-shot + `kd attach council` approach.

## Open Questions

- Should `kd breakdown --apply` default to dry-run unless `--yes` or
  `--confirm` is provided, or should it prompt by default?
- Should “checked” tickets be treated as “already applied”, or strictly ignored
  (recommended: ignore)?

