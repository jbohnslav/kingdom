# Plan: Kingdom MVP (Implementation Tickets)

## Goal
Deliver the minimum useful workflow: start a feature run, talk to the Hand in a persistent tmux window, generate an editable `plan.md` via the Council, convert approved plan items into `tk` markdown tickets, and hand off a single ticket to a Peasant worktree.

## Tickets
- [x] T1: Add `kd` CLI skeleton + command routing
  - Priority: 0
  - Depends on: none
  - Description:
    - Create the Python package layout and `typer` CLI entrypoint for `kd`.
    - Wire subcommands for the MVP surface area: `start`, `chat`, `council`, `plan`, `peasant`, `dev`, `status`, `attach`.
  - Acceptance:
    - [ ] `kd --help` works and lists MVP commands.
    - [ ] Each MVP command has a help/usage string and returns a non-zero exit code on bad input.

- [x] T2: Implement `.kd/` run state layout + read/write helpers
  - Priority: 0
  - Depends on: T1
  - Description:
    - Implement the MVP state layout from `docs/MVP.md`:
      - `.kd/config.json`, `.kd/current`, `.kd/runs/<feature>/state.json`, `.kd/runs/<feature>/plan.md`, `.kd/runs/<feature>/logs/*.jsonl`
    - Add small helpers to:
      - Create directories idempotently
      - Read/write JSON state files
      - Resolve the "current" run (from `.kd/current`) and validate it exists
  - Acceptance:
    - [ ] Running `kd start <feature>` creates `.kd/` and `.kd/runs/<feature>/` consistently.
    - [ ] Missing/invalid `.kd/current` yields a clear error for commands that require an active run.

- [x] T3: Add tmux orchestration helpers (server/session/windows)
  - Priority: 0
  - Depends on: T1
  - Description:
    - Adopt the namespacing approach in `docs/tech-stack.md` (server per repo, session per feature).
    - Implement helpers to:
      - Derive tmux server name for the current repo (e.g. `kd-kingdom`)
      - Create/select a session for `<feature>`
      - Create windows by fixed name (`hand`, `council`, `peasant-1`)
      - Attach to a session/window deterministically
  - Acceptance:
    - [ ] `kd start <feature>` creates (or reuses) a tmux session without clobbering existing unrelated sessions.
    - [ ] `kd attach hand` (once implemented) reliably attaches to the correct tmux server/session for the current repo/run.

- [x] T4: Implement `kd start <feature>` (initialize run + tmux session)
  - Priority: 0
  - Depends on: T2, T3
  - Description:
    - Follow `docs/MVP.md` workflow step 1:
      - Initialize `.kd/runs/<feature>/` state
      - Set `.kd/current` to `<feature>`
      - Initialize git branch behavior (at minimum, ensure you are on a feature branch; exact policy can be decided during implementation)
      - Start tmux session and create the `hand` window
  - Acceptance:
    - [ ] `kd start oauth-refresh` creates `.kd/runs/oauth-refresh/` and sets `.kd/current`.
    - [ ] A tmux session exists with a `hand` window after `kd start`.

- [x] T5: Implement `kd chat` (persistent Hand window)
  - Priority: 0
  - Depends on: T3, T4
  - Description:
    - Follow `docs/MVP.md` workflow step 2:
      - Attach to the `hand` window for the current run
      - Ensure the window is created if missing
      - Define the MVP "Hand" behavior: which CLI is launched there (or whether it is a shell with instructions)
    - Write Hand logs to `.kd/runs/<feature>/logs/hand.jsonl` (MVP can be minimal: append-only, best-effort).
  - Acceptance:
    - [ ] `kd chat` attaches to the same persistent Hand window across invocations.
    - [ ] Hand output is written to `.kd/runs/<feature>/logs/hand.jsonl` (or a clearly-documented MVP alternative).

- [x] T6: Implement `kd council` (claude/codex/agent + synthesis panes)
  - Priority: 1
  - Depends on: T3, T4
  - Description:
    - Follow `docs/MVP.md` "Council Commands":
      - Create a `council` window with panes for `claude`, `codex`, `agent`, and a synthesis pane
      - Run the three model CLIs "in parallel" (tmux panes) using the same prompt
      - Default synthesis to `claude` unless configured otherwise
    - Persist logs to `.kd/runs/<feature>/logs/council.jsonl` (MVP can store pane outputs independently if easier).
  - Acceptance:
    - [ ] `kd council` opens a `council` window with the expected panes.
    - [ ] Each pane runs its configured CLI command (or clearly errors with actionable guidance if the CLI is missing).

- [x] T7: Implement `kd plan` (Council-backed plan drafting into `plan.md`)
  - Priority: 0
  - Depends on: T2, T6
  - Description:
    - Follow `docs/MVP.md` workflow step 3 and "Plan File Format":
      - Create/update `.kd/runs/<feature>/plan.md` as the single source of truth
      - Use the suggested structure: `Goal`, `Tickets`, `Revisions`
      - While planning is active, update `plan.md` in place; after work begins, append under `## Revisions`
    - Decide MVP ergonomics:
      - How the Council output is gathered into `plan.md` (copy/paste flow vs. capture pane outputs)
      - How "plan approved" is represented (e.g., explicit prompt, a marker in state.json, or a `kd plan --approve`)
  - Acceptance:
    - [ ] `kd plan` produces `.kd/runs/<feature>/plan.md` in the documented format.
    - [ ] Re-running `kd plan` updates the existing plan (and uses `## Revisions` after dev starts, per MVP policy).

- [x] T8: Implement ticket creation from `plan.md` via `tk` (markdown tickets only)
  - Priority: 0
  - Depends on: T7
  - Description:
    - Follow `docs/MVP.md` "Ticket Creation" mapping:
      - Parse `plan.md` `## Tickets` into `tk create ...` commands
      - Apply priority, acceptance, and dependencies (`tk dep`)
      - Ask for approval before applying changes
    - Define where tickets live (expected `.tickets/` repo directory) and how the plan stores the created ticket ids.
  - Acceptance:
    - [ ] With a sample `plan.md`, the system can generate a dry-run list of `tk` commands.
    - [ ] With approval, tickets are created as markdown files and dependencies are applied.

- [x] T9: Implement `kd peasant <ticket>` (single-ticket worktree + tmux window)
  - Priority: 0
  - Depends on: T2, T3, T4, T8
  - Description:
    - Follow `docs/MVP.md` workflow step 6:
      - Create a git worktree for the ticket (MVP: one Peasant only, `peasant-1`)
      - Create a `peasant-1` window and start the chosen agent CLI in that worktree
      - Record which ticket is assigned in `.kd/runs/<feature>/state.json`
  - Acceptance:
    - [ ] `kd peasant <ticket-id>` creates a worktree and starts `peasant-1` in tmux.
    - [ ] The Peasant runs in the correct working directory (the ticket worktree).

- [x] T10: Implement `kd status` (current phase + tickets + tmux overview)
  - Priority: 1
  - Depends on: T2, T3, T8, T9
  - Description:
    - Follow `docs/MVP.md` "Commands":
      - Show current run/phase (from `.kd/current` and `.kd/runs/<feature>/state.json`)
      - Show ticket summary (using `tk` where available)
      - Show which tmux windows exist and whether Peasant is active
  - Acceptance:
    - [ ] `kd status` is useful without attaching to tmux: it reports what's running and what the next action is.

- [x] T11: Implement `kd attach <target>` (hand/council/peasant-1)
  - Priority: 1
  - Depends on: T3, T4, T6, T9
  - Description:
    - Follow `docs/MVP.md` "Commands":
      - `kd attach hand|council|peasant-1` attaches to the named window for the current run
      - Provide clear errors when the target doesn't exist (and optionally offer to create it)
  - Acceptance:
    - [ ] `kd attach hand` / `kd attach council` / `kd attach peasant-1` attach reliably for the current run.

- [x] T12: Implement `kd dev` as a reserved/stub command (MVP-safe behavior)
  - Priority: 2
  - Depends on: T1, T9
  - Description:
    - Follow `docs/MVP.md` scope note:
      - Keep `kd dev` reserved for later, but make it non-confusing in MVP.
      - MVP behavior options: print guidance and exit, or delegate to `kd peasant` when invoked with a ticket.
  - Acceptance:
    - [ ] `kd dev` does not start parallel Peasants or introduce non-MVP behavior.
    - [ ] The output clearly tells the user what to do in MVP (`kd peasant <ticket>`).

- [x] T13: MVP docs + smoke tests
  - Priority: 2
  - Depends on: T1, T4, T7, T9
  - Description:
    - Update docs to reflect actual CLI behavior (especially any deviations from `docs/MVP.md`).
    - Add smoke tests (or a `make smoke` script) covering:
      - `kd start` creates expected state layout
      - `kd plan` creates/updates `plan.md`
      - `kd peasant` creates a worktree path deterministically (can be stubbed if tmux/agents absent in CI)
  - Acceptance:
    - [ ] A new developer can follow docs to run through: `kd start` -> `kd chat` -> `kd plan` -> `tk` tickets -> `kd peasant`.
