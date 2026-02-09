---
id: kin-9a32
status: open
deps: []
links: []
created: 2026-02-09T18:48:16Z
type: task
priority: 1
---
# Harness logging and quality gates

The harness (agent loop in harness.py) has three problems found during the kin-41f9 smoke test: agent output is invisible in logs, quality gates don't match review, and failure details are swallowed.

## 1. Agent output must flow to logs

`kd peasant logs --follow` should feel like watching the agent work in a terminal — seeing what it reads, edits, and thinks. Currently only harness wrapper lines appear ("Iteration N", "CONTINUE", "DONE"). The actual agent CLI stdout/stderr must be piped through to the log files.

## 2. Quality gates must match review

`run_tests()` only runs pytest. `kd peasant review` runs pytest + ruff. Peasant claims DONE, passes the harness check, then gets bounced by review. The harness DONE condition must run both `pytest` and `ruff check` before accepting.

## 3. Failure details must be logged

When overriding DONE to CONTINUE, the harness logs "Tests failed, overriding DONE to CONTINUE" with no detail. The actual pytest/ruff output (which tests failed, what lint errors) must be included so debugging from `kd peasant logs` is possible.

## Acceptance Criteria

- [ ] `kd peasant logs --follow` shows the agent's actual CLI output, not just harness bookkeeping
- [ ] Harness DONE check runs both pytest and ruff check (matching `kd peasant review`)
- [ ] When tests or lint fail, the full failure output is logged (visible in `kd peasant logs`)
- [ ] Peasant that passes harness DONE check also passes `kd peasant review` gates
