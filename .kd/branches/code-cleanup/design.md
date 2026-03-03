# Design: code-cleanup

## Goal

Clean up, restructure, and simplify the kingdom codebase. Break apart the
monolithic CLI, remove dead code and legacy paths, consolidate duplicated
patterns, redesign the command surface, and bring documentation in sync with
reality. No backwards compatibility — this is a breaking cleanup.

## Context

We've been shipping features fast — the CLI grew from a handful of commands to
62 decorators across 4,960 lines in a single `cli.py`. Business logic, git
orchestration, rendering, and argument parsing are tangled together. The library
layer (`ticket.py`, `thread.py`, `state.py`) is actually clean, but the CLI
bypasses it in places, reimplementing filtering and status computation inline.

Meanwhile docs have drifted: `multi-agent-redesign.md` describes commands that
never shipped (`kd send`, `kd agent start/stop`), `cli-skill-architecture.md`
references removed commands (`council critique`, `council doctor`, `--open`
flag), and the README only covers ~10 of 40+ real commands.

The `runs/` → `branches/` migration left dual-path fallback logic in 6+ places
across `state.py` and `cli.py`. Dead code (`kd dev` stub, deprecated `run_root`
helpers, stale `.pyc` files) adds noise. And a few structural issues in the data
layer — `find_ticket()` ambiguity, no dedup in `collect_all_tickets()`,
priority-0-as-falsy bug — have been documented but not fixed.

### By the numbers

| File | Lines | What's in there |
|------|-------|-----------------|
| `cli.py` | 4,960 | All 40+ commands, worktree mgmt, council watch, peasant review, ticket rendering, filtering |
| `test_cli_ticket.py` | 3,087 | Ticket CLI tests — lifecycle, deps, list, query all mixed |
| `test_cli_peasant.py` | 1,840 | Peasant CLI tests with heavy subprocess mocking |
| `test_cli_council.py` | 1,589 | Council CLI tests with filesystem-based stream fixtures |
| Library layer | 3,995 | `ticket.py` + `thread.py` + `state.py` + `config.py` + `session.py` + `parsing.py` — clean and well-factored |

The library layer is 55% the size of the CLI alone. The CLI should be a thin
shell over it, not the other way around.

## Command Surface Redesign

No backwards compatibility. We are breaking the CLI surface intentionally.

### Commands to delete

| Command | Reason |
|---------|--------|
| `kd init` | Auto-init inside `kd start` when `.kd/` doesn't exist |
| `kd dev` | Dead stub, just prints "use `kd peasant start`" |
| `kd work` | Internal harness, not user-facing |
| `kd whoami` | Low value, noisy surface |
| `kd migrate` | No migration support — hard cut |
| `kd chat` | Moved to `kd council chat` |
| `kd breakdown` | Moved to skill-only (auto-discovered by kingdom skill) |
| `kd setup-skill` | Folded into `kd start` (auto-setup when missing) |
| `kd tk ready` | Folded into `kd tk list --ready` |
| `kd tk closed` | Folded into `kd tk list --closed` |
| `kd tk blocked` | Folded into `kd tk list --blocked` |
| `kd tk query` | Folded into `kd tk list --json --jq` |
| `kd tk dep` | Replaced by `kd tk deps add` |
| `kd tk undep` | Replaced by `kd tk deps remove` |
| `kd tk dep-tree` | Replaced by `kd tk deps tree` |
| `kd tk dep-cycle` | Replaced by `kd tk deps cycle` |

### Commands to move/merge

| Old | New | Notes |
|-----|-----|-------|
| `kd chat` | `kd council chat` | Chat is council functionality |
| `kd breakdown` | *(deleted from CLI)* | Kingdom skill handles this |
| `kd design` (default) | `kd design` | Prints path to design doc (for agents) |
| `kd design show` | `kd design show` | Renders design doc in terminal (for humans) |
| `kd tk dep/undep/dep-tree/dep-cycle` | `kd tk deps add/remove/tree/cycle` | Group under `deps` subcommand |

### Commands to keep as-is

| Command | Notes |
|---------|-------|
| `kd start` | Now also auto-inits `.kd/` and auto-runs setup-skill |
| `kd done` | Optional checkpoint — "are all tickets closed?" |
| `kd status` | Core workflow command |
| `kd doctor` | Useful diagnostics |
| `kd config` | Configuration management |
| `kd design approve` | Kept |
| `kd tk create/list/show/start/current/close/reopen` | Core ticket lifecycle |
| `kd tk move/pull` | Keep `pull` as shorthand for "grab from backlog" |
| `kd tk link/unlink` | Keep flat — only 2 commands, no need to group |
| `kd tk assign/unassign` | Kept |
| `kd tk add-note/log/edit` | Kept |
| `kd ticket ...` | Keep as alias for `kd tk` |
| `kd council ask/show/list/status/watch/retry/review/reset/chat` | Full council surface (chat moved here from top-level) |
| `kd peasant start/stop/sync/review/clean/msg/read/watch/logs` | Keep flat — all verbs do one obvious thing |

### Hidden aliases to keep

- `kd tk ls` → `kd tk list`
- `kd council ls` → `kd council list`

### Final top-level surface

```
Top-level:  start, done, status, doctor, config
Namespaces: tk (alias: ticket), council, peasant, design
```

## Requirements

### R1. Redesign command surface

Implement the command matrix above:

1. Delete: `init`, `dev`, `work`, `whoami`, `migrate`, `chat`, `breakdown`,
   `setup-skill`.
2. Fold `setup-skill` behavior into `kd start` (auto-setup when `.kd/` missing
   or skill not installed).
3. Fold `init` behavior into `kd start` (auto-init `.kd/` if not present).
4. Move `chat` to `kd council chat`.
5. Create `kd tk deps` sub-app with `add`, `remove`, `tree`, `cycle` subcommands.
   Delete the old `dep`, `undep`, `dep-tree`, `dep-cycle` commands.
6. Remove standalone `kd tk ready`, `kd tk closed`, `kd tk blocked`, `kd tk query`.
   Add `--ready`, `--closed`, `--blocked`, `--json`, `--jq` flags to `kd tk list`.
   `--json` outputs the same ticket schema that `tk query` uses today (all
   non-closed tickets by default). `--jq EXPR` takes an optional jq filter
   expression applied to the JSON output. When `--closed` is combined with
   `--json`, closed tickets are included in the output.
7. Keep `kd design` as "print path", keep `kd design show` as "render in
   terminal", keep `kd design approve`.

### R2. Split `cli.py` into domain modules

Break the monolith into a `kingdom/cli/` package:

```
kingdom/cli/
  __init__.py      # root app, callback, top-level commands (start, done, doctor, status)
  ticket.py        # kd tk ... (all ticket subcommands including deps sub-app)
  council.py       # kd council ... (ask, show, list, status, watch, retry, review, reset, chat)
  peasant.py       # kd peasant ... (start, stop, sync, review, clean, msg, read, watch, logs)
  design.py        # kd design (path, show, approve)
  config.py        # kd config ...
  display.py       # shared rendering: ticket tables, panels, status formatting
  helpers.py       # resolve_ticket_or_exit(), shared CLI utilities
```

Each module registers its own Typer sub-app. The root `__init__.py` mounts them.

### R3. Extract domain logic out of the CLI layer

Move business logic that currently lives in CLI functions back to library
modules:

- **Worktree management** (~110 lines): `create_worktree`, `remove_worktree`,
  `worktree_path_for` → new `kingdom/worktree.py`
- **Ticket filtering** (`apply_filters`, `apply_priority`): closures inside
  CLI commands → pure functions in `ticket.py`
- **Ticket status computation**: `ticket_ready` reimplements its own collection
  traversal → use `collect_all_tickets` from `ticket.py`
- **Worklog pure logic**: `append_worklog_entry` mixes markdown manipulation
  with I/O → extract pure string transform, keep I/O in caller

### R4. Kill legacy `runs/` fallback — hard cut

1. Delete all dual-path fallback logic from `state.py` (`logs_root`,
   `sessions_root`, `tickets_root`) and `cli.py`.
2. Remove deprecated `run_root`, `runs_root`, `ensure_run_layout` from
   `state.py`.
3. Stop creating `.kd/runs/` in `ensure_base_layout`.
4. If `.kd/runs/` exists, fail fast with a clear error message telling the
   user to manually rename it. No `kd migrate`, no auto-migration.

### R5. Consolidate duplicated patterns

- **`resolve_ticket_or_exit(base, ticket_id)`**: Replace the ~10 identical
  `try: find_ticket() / except AmbiguousTicketMatch` blocks with one helper
  in `cli/helpers.py`.
- **`parse_iso_datetime(s)`**: Replace 3+ inline `"Z"` → `"+00:00"`
  conversions with a single utility in `parsing.py`.
- **`serialize_frontmatter(fields)`**: Unify hand-built YAML frontmatter in
  `ticket.py` and `thread.py` into a shared helper in `parsing.py`.

### R6. Remove non-command dead code

Command deletions are handled by R1. This requirement covers everything else:

- Stale `.pyc` files: `hand.cpython-312.pyc`, `plan.cpython-312.pyc`,
  `planning.cpython-312.pyc`, `tmux.cpython-312.pyc`,
  `council_worker.cpython-312.pyc`
- Deprecated functions in `state.py`: `run_root`, `runs_root`,
  `ensure_run_layout` (also covered by R4, but listed here for completeness)

### R7. Fix the global mutable state

Replace the module-level `VERBOSE: bool = False` global with Typer's context
object or a simple context dataclass threaded through commands.

### R8. Fix known data-layer bugs

- **Priority-0-as-falsy** (`parse_ticket`): `if priority:` skips priority 0.
  Fix to `if priority is not None:`.
- **`find_ticket` ambiguity** (ticket `aa61`): Prefer current branch → backlog
  → archive before raising `AmbiguousTicketMatch`. Return a `TicketMatch`
  with location info.
- **`collect_all_tickets` dedup**: Deduplicate by ticket ID, preferring
  branch copy over backlog/archive.
- **Deps/links uniqueness**: Normalize to ordered sets after parsing.

### R9. Bring docs in sync

- **Retire or mark as historical**: `multi-agent-redesign.md`,
  `council-design.md` (describes architecture that was never built exactly as
  specified).
- **Update `cli-skill-architecture.md`**: Remove references to `council
  critique`, `council doctor`, `--open` flag. Add real command surface.
- **Update README**: Add a CLI reference section or link to `kd --help` output.
  Cover peasant lifecycle, ticket dependencies, council watch/retry.
- **Update the kingdom skill** (`skills/kingdom/SKILL.md`): Ensure it reflects
  actual commands after the surface redesign.
- **Update AGENTS.md**: Reflect new command surface (especially `council chat`
  replacing top-level `chat`).

### R10. Consolidate test fixtures and reorganize tests

- Move the `project` fixture (duplicated 8+ times) into `conftest.py`.
- Split `test_cli_ticket.py` into logical groups (lifecycle, list, deps,
  links, worklog).
- Tests should import from `kingdom.cli.ticket` etc. rather than the monolith.
- Update all test imports after the CLI split.

## Decisions

- **No backwards compatibility** (except explicitly retained aliases): This is
  a breaking change. Removed commands are deleted, not aliased. Users of
  `.kd/runs/` get a hard error, not a migration path. The only kept aliases are
  `kd ticket` (for `kd tk`) and hidden `ls` shorthands — these are intentional
  convenience, not compatibility shims.
- **Package, not file**: `cli.py` → `cli/` package (not just splitting into
  `cli_ticket.py`, `cli_council.py` siblings). A package is cleaner for Typer
  sub-app mounting and matches the test file structure we already have.
- **No new abstractions for git**: Skip a `GitOps` helper class — it's
  premature abstraction. The git calls are straightforward `subprocess.run`
  invocations. Tests already mock `subprocess.run` directly.
- **Hard cut over migration**: Rather than maintaining backward compatibility
  or building a migration tool, fail fast if old layout detected. Users rename
  manually (it's a directory rename).
- **`resolve_ticket_or_exit` in CLI layer, not library**: This helper raises
  `typer.Exit`, which is CLI-specific. It belongs in `cli/helpers.py`, not in
  `ticket.py`. The library layer should keep raising `AmbiguousTicketMatch`.
- **Skill replaces `breakdown` CLI command**: The kingdom skill already knows
  how to generate the breakdown prompt. No need for a dedicated CLI command.
- **Docs: update, don't delete**: Historical design docs get a clear
  `> **Historical** — this document describes an earlier design. See README for
  current commands.` banner rather than deletion, preserving design rationale.
- **Keep peasant commands flat**: No `inspect`/`control` grouping — each
  peasant subcommand is a verb that does one obvious thing. The problem was
  documentation, not surface area.
- **Keep `kd tk pull`**: Natural verb for "grab from backlog." Don't force
  `move --from backlog --to current` for the most common move operation.
- **Keep `kd done`**: Optional but useful checkpoint. Better than hiding its
  checks inside `kd start` where they don't conceptually belong.

## Execution Order

The refactors have dependencies. Proposed order:

1. **R6 (non-command dead code)** — smallest, safest, reduces noise for
   everything after. Stale `.pyc` files and deprecated `state.py` functions.
2. **R1 (command surface redesign)** — delete/move/merge commands while still
   in one file (easier to see the full picture).
3. **R5 (consolidate patterns)** — introduce shared helpers before the big split
   so the split is cleaner.
4. **R2 (split cli.py)** — the main event. Mechanical move, then verify all
   tests pass with updated imports.
5. **R3 (extract domain logic)** — now that CLI modules are small, it's easy to
   spot and extract logic that doesn't belong.
6. **R4 (kill legacy runs/)** — hard cut, delete all fallback paths.
7. **R7 (global state)** — small fix, do alongside R2 or after.
8. **R8 (data-layer bugs)** — independent of CLI split, can be done in parallel.
9. **R10 (test fixtures)** — after CLI split, reorganize tests to match.
10. **R9 (docs)** — last, once the code is stable.
