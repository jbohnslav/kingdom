---
id: "bc0c"
status: open
deps: []
links: []
created: 2026-08-03T12:43:00Z
type: task
priority: 2
---
# Fail fast on non-recoverable peasant authentication errors

## Acceptance Criteria

- [ ] Authentication and other clearly non-recoverable provider failures stop
  the peasant after the first failed attempt.
- [ ] Transient failures use bounded backoff rather than a tight retry loop.
- [ ] The final peasant status and worklog distinguish infrastructure failure
  from agent implementation/review failure.
- [ ] A diagnostic points to the relevant host authentication command or
  `kd doctor` check.

## Context

During the `92ca` dogfood run, an expired Claude OAuth token produced the same
401 on 39 consecutive iterations in roughly two minutes. No implementation work
was possible, yet the harness kept consuming iterations until manually stopped.
This is separate from backlog ticket `bd1f`, which expands doctor diagnostics;
this ticket owns runtime retry classification and fail-fast behavior.
