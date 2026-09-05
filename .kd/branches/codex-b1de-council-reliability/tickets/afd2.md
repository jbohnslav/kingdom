---
id: "afd2"
status: closed
deps: []
links: []
created: 2026-07-10T13:32:00Z
type: bug
priority: 2
closed_at: 2026-08-24T19:52:04Z
resolution: completed
closed_context: codex:f1fe48bc0e4e0556
assignee: codex:f1fe48bc0e4e0556
parent: b1de
---
# Handle council ask without an active session gracefully

Running kd council ask without an active session raises RuntimeError and prints a full Rich traceback. Expected: concise user-facing error telling the user to run kd start or switch to a tracked branch, with a nonzero exit code and no traceback.

## Acceptance Criteria

- [x] `kd council ask` outside an active session exits 1 without a Python traceback.
- [x] Output explains that no active session is selected and gives the exact `kd start <feature>` recovery.
- [x] A regression covers the no-session path before Council creation or provider dispatch.
- [x] Focused tests, Ruff/format checks, diff validation, and manual working-tree CLI output pass.

## Worklog

- [2026-08-24 15:39] [codex:f1fe48bc] — Started after closing the first four verified children. Reproduce the no-session traceback with a failing regression, apply the concise Council CLI boundary pattern, run full verification, and manually inspect output.
- [2026-08-24 15:40] [codex:f1fe48bc] — Regression reproduced: no-session Council ask exits through an uncaught RuntimeError and emits no concise CLI guidance under CliRunner.
- [2026-08-24 15:41] [codex:f1fe48bc] — Implemented the same explicit CLI boundary used by `council list`: catch no-session resolution, print the canonical `kd start <feature>` guidance, and exit 1 without provider setup or traceback. Regression failed first, then all 12 `TestCouncilAsk` tests passed. Ruff/format and diff checks passed. Manual working-tree invocation printed the expected one-line error and exited 1. Full-suite verification remains before closure.
- [2026-08-24 15:52] [codex:f1fe48bc] — Owner review complete. Final combined verification passed: uv run pytest (2272 passed, 41 skipped, 1 xfailed), repository-wide Ruff check and format check, git diff --check, and manual no-session Council ask output.

## Lifecycle

- 2026-08-24T19:52:04Z [codex:f1fe48bc0e4e0556] — closed (completed)
