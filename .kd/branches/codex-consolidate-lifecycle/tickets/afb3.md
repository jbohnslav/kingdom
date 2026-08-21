---
id: "afb3"
status: closed
deps: []
links: []
created: 2026-08-21T13:57:41Z
type: task
priority: 2
closed_at: 2026-08-21T14:18:42Z
resolution: completed
close_reason: "Implemented explicit, globally consistent dependency readiness across ticket readouts and orchestration."
closed_context: codex:a775e0448cdb5a76
assignee: codex:a775e0448cdb5a76
---
# Make dependency readiness explicit when showing tickets

## Acceptance Criteria

- [x] Default `kd tk show <id>` output resolves every dependency status instead of exposing only raw dependency IDs.
- [x] Ticket readout explicitly distinguishes "blocked by open/unknown dependencies" from "not blocked; all dependencies closed."
- [x] Agent guidance forbids inferring a blocker from the presence of a dependency edge alone and points to state-aware inspection.
- [x] Human, JSON, and default ticket-reading surfaces remain consistent, with red-first regression coverage and full project verification.

## Reported Failure

An agent summarized open epic `5b81` as "Blocked by dependency b931" solely
because `b931` appeared in `deps`. A follow-up lookup showed the dependency was
already closed. At report time, the default raw `kd tk show` output exposed the
edge without the resolved state, while `--rich` and `--json` included status.

## Worklog

- [2026-08-21 10:05] [codex:a775e044] — Red-first regression: added four focused assertions for closed dependency readiness, mixed open/closed blockers, rich gate output, and JSON gate metadata. The initial run failed 4/4 because default output exposed only raw IDs, rich output lacked an explicit gate, and JSON lacked `dependency_gate`.

  Implemented one shared dependency-resolution path for default, rich, JSON, and current-ticket output. Default `kd tk show` now appends each resolved dependency status and an explicit gate: closed-only dependencies are `clear — not blocked`, while non-closed or unknown dependencies are named as blockers. Updated the Kingdom skill, ticket reference, and worker/lord prompt copy so agents do not infer blocking from an edge alone.

  Focused verification: 40 show/skill tests passed, then 313 show/current/deps/harness/lord/skill tests passed. Ruff check and format checks passed; `git diff --check` passed. Manual isolated-repository smoke produced `3e97 (closed)` and `Dependency gate: clear — not blocked; all dependencies are closed.`
- [2026-08-21 10:11] [codex:a775e044] — Independent review found that the first implementation's authoritative gate wording exposed a pre-existing cross-location inconsistency: `show` resolved dependencies globally, but list readiness, peasant launch, and lord scheduling/snapshots could treat closed dependencies from another workspace or archive as unknown blockers. Added red regressions across those surfaces; 4 failed and 3 already-green structured readout checks passed.

  Moved dependency status collection/resolution/blocker classification into shared ticket-domain helpers. Readiness now consults live branches, done workspaces, backlog, and archive consistently in show/current/list/peasant/lord. Added mixed open/closed/unknown JSON blocker coverage, explicit unknown blocker and current output checks, archived dependency readiness coverage, and cross-workspace peasant/lord coverage. The affected 381-test suite now passes with Ruff and diff checks green. Awaiting independent re-review before final gates.
- [2026-08-21 10:15] [codex:a775e044] — Second independent review found two remaining readiness consistency edges and one documentation mismatch. `find_newly_unblocked()` still used partial statuses, and global collection did not explicitly preserve current-workspace precedence when duplicate IDs exist; the recovery text also incorrectly implied `tk close` enforces dependency readiness.

  Added red-first regression coverage for archived prerequisites in unblocked notifications and current-workspace duplicate precedence (1 failed, 1 already passed under the local filesystem order). Updated all-ticket collection to order the current workspace first deterministically, reused global statuses for unblocked detection, and corrected the recovery text to describe work readiness. The expanded affected suite passed: 542 passed, 3 skipped, with Ruff, formatting, and diff checks green. Sent the result for a final independent re-review.
- [2026-08-21 10:18] [codex:a775e044] — Final independent re-review reported no remaining actionable issues and confirmed all prior findings resolved. The full suite exposed an unrelated doctor JSON test that failed intermittently only while another test process touched real host integrations; the test scoped config/state but not `Path.home`. Isolated that test's home directory like the adjacent doctor test so concurrent verification cannot leak host state into a model-reporting assertion.

  Final verification after all fixes: 2,217 passed, 38 skipped, 1 expected xfail. Repository-wide Ruff check and format check passed, all pre-commit hooks passed, `git diff --check` passed, and `bash scripts/smoke.sh` completed the public ticket lifecycle with readiness ready. All acceptance criteria are satisfied.
- [10:18] [codex:a775e0448cdb5a76] — Closed: Implemented explicit, globally consistent dependency readiness across ticket readouts and orchestration.

## Lifecycle

- 2026-08-21T14:18:42Z [codex:a775e0448cdb5a76] — closed (completed): Implemented explicit, globally consistent dependency readiness across ticket readouts and orchestration.
