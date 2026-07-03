---
id: "ca9d"
status: closed
deps: []
links: []
created: 2026-07-03T21:57:35Z
type: bug
priority: 2
closed_at: 2026-07-03T22:01:25Z
assignee: hand
---
# Validate terminal ticket context before Stop hook uses it

## Acceptance Criteria

- [x] Stop hook only trusts terminal-local ticket context when the recorded ticket is still in_progress on the current branch
- [x] Stale, closed, missing, or moved terminal-context tickets fall back to kd tk current
- [x] Regression tests cover stale closed terminal context

## Worklog

- [2026-07-03 17:59] — Addressed Claude/Codex PR review feedback: `find_stop_ticket_id()` now validates terminal-local context by reading the recorded ticket from the current branch and requiring it to still be `in_progress` before using it. Closed, missing, or moved tickets fail validation and fall back to `kd tk current --id --exclude-peasant`. Updated hook tests to create real branch ticket files and added a stale-closed regression test. Verification so far: `uv run pytest -q tests/test_hook.py` passed with 44 tests, and `uv run ruff check src/kingdom/cli/hook.py tests/test_hook.py` passed.
- [2026-07-03 18:00] — Full verification passed: `uv run ruff check`; `uv run pytest -q` with 1911 passed, 38 skipped, 1 xfailed.
- [18:01] — Closed: Validated terminal-local Stop hook context before use and added stale-closed regression coverage. Full ruff and pytest pass.
