---
id: "bc0c"
status: closed
deps: []
links: []
created: 2026-08-03T12:43:00Z
type: task
priority: 2
closed_at: 2026-08-03T19:02:37Z
resolution: completed
closed_context: codex:a775e0448cdb5a76
assignee: codex:a775e0448cdb5a76
---
# Fail fast on non-recoverable peasant authentication errors

## Acceptance Criteria

- [x] Authentication and other clearly non-recoverable provider failures stop
  the peasant after the first failed attempt.
- [x] Transient failures use bounded backoff rather than a tight retry loop.
- [x] The final peasant status and worklog distinguish infrastructure failure
  from agent implementation/review failure.
- [x] A diagnostic points to the relevant host authentication command or
  `kd doctor` check.

## Context

During the `92ca` dogfood run, an expired Claude OAuth token produced the same
401 on 39 consecutive iterations in roughly two minutes. No implementation work
was possible, yet the harness kept consuming iterations until manually stopped.
This is separate from backlog ticket `bd1f`, which expands doctor diagnostics;
this ticket owns runtime retry classification and fail-fast behavior.

## Worklog

- [2026-08-03 14:59] [codex:a775e044] — Red-first coverage reproduced the 92ca failure mode: an expired OAuth response was invoked 50 times, while transient errors stopped immediately and AgentState could not represent the failure cause. The harness now classifies authentication, permanent provider, transient, and generic backend failures before agent output handling. Authentication and clearly permanent failures stop after one attempt with backend-specific re-authentication or kd doctor guidance; transient failures retry at most three times with 1s/2s backoff. Session status persists failure_kind and peasant status exposes it in JSON and human output. Focused verification passed: four provider retry tests, the CLI failure-kind test, all 35 session tests, Ruff check, and format check. Manual peasant status inspection confirmed the new JSON field and unchanged table layout for healthy sessions.
- [2026-08-03 15:02] [codex:a775e044] — Parent review passed: full suite 2172 passed, 38 skipped, 1 expected failure; whole-tree Ruff check and format check passed; all pre-commit hooks passed without rewriting files.

## Lifecycle

- 2026-08-03T19:02:37Z [codex:a775e0448cdb5a76] — closed (completed)
