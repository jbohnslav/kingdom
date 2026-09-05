---
id: "eb2c"
status: closed
deps: [f122, 2877]
links: []
created: 2026-08-02T13:58:23Z
type: task
priority: 2
closed_at: 2026-08-03T15:53:52Z
resolution: completed
closed_context: codex:a775e0448cdb5a76
assignee: codex:0f4ec9f976ec982b
parent: 329d
---
# Make kd start idempotent and ticket-epic-first

Let `kd start` initialize or resume the workspace without asserting that one branch,
one design document, and one current task are the whole unit of work.

## Acceptance Criteria

- [x] Running `kd start` in an initialized workspace is safe and reports what already exists.
- [x] The default path does not scaffold or require `design.md`.
- [x] Existing branch/backlog organization and `tk pull` remain supported.
- [x] Multiple execution contexts can start different tickets on the same branch.
- [x] Any retained `.kd/current` meaning is documented as a branch/workspace default, not session identity.
- [x] Manual output gives a short useful next action.

## Worklog

- 2026-08-03 — Started with `uv run kd tk start eb2c`. Added regression
  coverage before implementation for ticket-first branch layout, idempotent
  resume, preserving an existing legacy design, changing the repository workspace
  default without `--force`, ticket counts, and state-aware next-action output.
  Baseline command:
  `uv run pytest -q tests/test_init.py tests/test_state.py` → 5 expected failures,
  102 passes. Failures prove current `kd start` still scaffolds design/breakdown,
  rejects both same-branch resume and a different workspace default, and advertises
  a design path.
- 2026-08-03 — Implemented the ticket/epic-first start path in
  `src/kingdom/cli/__init__.py` and `src/kingdom/state.py`. `kd start` now creates
  or resumes branch runtime directories without design/breakdown files, preserves
  legacy planning files if present, updates `.kd/current` as a repository fallback
  rather than a session lock, and reports branch/backlog ticket counts. The
  compatibility `--force` flag remains accepted but is unnecessary. Start/switch
  help and `set_current_run()` now document that execution-context bindings are
  independent of the repository default.
- 2026-08-03 — Parent review caught a misleading next action when every branch
  ticket was closed or blocked. Added failing regressions, then made the output
  state-aware: ready work → `tk list --ready`, active work → `kd status`, blocked
  work → `tk list --blocked`, backlog-only work → list/pull, otherwise create a
  ticket with an epic hint.
- 2026-08-03 — Verification:
  `uv run pytest -q tests/test_init.py tests/test_state.py` → 109 passed;
  broader CLI/design/status/five-context/ticket-pull/done/epic/worktree suite →
  244 passed; Ruff check and format check passed on all four changed Python/test
  files. Manual dogfood in a fresh temporary Git repository showed no planning
  files, `Started workspace`, `0 branch, 0 backlog`, and a create/epic next action;
  after `kd tk create --type epic`, the second `uv run kd start` reported
  `Resumed workspace`, `1 branch`, and `kd tk list --ready`. No implementation
  code requires design approval, and the existing five-context integration test
  confirms independent contexts remain isolated on one branch.
- 2026-08-03 — Review correctness fix: start's first next-action calculation
  initially built dependency status from branch tickets only, so it could label a
  ticket blocked even while canonical `kd tk list --ready` considered it ready
  because the dependency was closed elsewhere. Added a failing regression with a
  dependency in a done branch, then switched start to the same shared
  `collect_all_tickets(base, include_done=True)` status lookup and
  `filter_tickets_by_deps()` used by ticket listing. This covers active branches,
  backlog, and done branches and deliberately matches current `tk list --ready`
  semantics; archived branch tickets are not part of that command's default
  lookup. Updated verification: start/layout suite **110 passed**; expanded
  CLI/ready-list/status/five-context/ticket-pull/done/epic/worktree suite
  **323 passed**; Ruff check and format check remain green.
- 2026-08-03 — Real-resume review found that `kd start` still called
  `install_skill()` for every existing workspace, adding host-install warnings and
  checking external host state before the otherwise-short summary. Added a red
  regression: the existing auto-init contract passed, while resume/new-branch
  starts called the installer twice. Moved installation into first `.kd/`
  auto-initialization only; explicit `kd update` remains the refresh path.
  Verification now: start/layout suite **111 passed**, broader suite **323
  passed**, Ruff check/format green. Manual command
  `uv run kd start codex/workflow-polish` now prints only `Resumed workspace`,
  location, `41 branch, 37 backlog`, and `kd tk list --ready`—no
  Claude/Codex/Cursor install checks or warnings.

- 2026-08-03 — Parent acceptance review reran the complete repository suite after
  the installer fix: **2,093 passed, 38 skipped, 1 xfailed**. Ruff lint and
  `git diff --check` pass. A final real
  `uv run kd start codex/workflow-polish` produced exactly the clean four-line
  resume summary with no host-install output.

## Lifecycle

- 2026-08-03T15:53:52Z [codex:a775e0448cdb5a76] — closed (completed)
