---
id: "bdbf"
status: open
deps: []
links: []
created: 2026-02-17T20:57:53Z
type: task
priority: 2
---
# Fix review findings: merge safety, duplicate harness, test gaps

## Findings

### HIGH

**1. `--accept` can merge into wrong git branch** (`src/kingdom/cli.py:2231-2275`)
`peasant review --accept` runs `git merge ticket/<id>` from the base repo but never validates or switches to the feature branch recorded in `.kd/current`. The merge target is whatever branch the user happens to have checked out. This can silently merge peasant work into the wrong branch (e.g., `main`). Fix: explicitly verify/checkout the feature branch before merging, or abort with a clear error if HEAD doesn't match.

**2. Merge recovery instructions wrong for hand-mode** (`src/kingdom/cli.py:2260`)
The error recovery message tells the user to `cd worktree_path` and `git merge feature`, but hand-mode peasants work directly in the main worktree — `worktree_path_for()` returns a path that doesn't exist. Recovery instructions should detect hand-mode and give the correct path.

### MEDIUM

**3. `--reject` always relaunches harness, risking duplicate workers** (`src/kingdom/cli.py:2278-2328`)
The new reject flow unconditionally spawns `kd work` without checking whether the previous harness is still alive. The old code gated relaunch on `os.kill(pid, 0)` liveness. Two concurrent harnesses on the same worktree will race over files and logs. Fix: restore the liveness check; only relaunch when the previous process is confirmed dead (or kill it first).

**4. Council-block feedback message not asserted in tests** (`tests/test_harness.py:1248-1273`)
`test_council_blocking_bounces_back` checks `review_bounce_count` and final status but never verifies that the `## Council Review Feedback (BLOCKING)` message was actually written to the work thread via `add_message`. A regression that breaks feedback delivery would pass this test silently. Fix: assert `add_message` was called with expected content, or check the thread file.

**5. Backlog move test checks output text, not file state** (`tests/test_cli_ticket.py:536-547`)
`test_move_to_backlog_shows_backlog_label` asserts CLI output says "Moved ... to backlog" but never checks that the ticket file actually moved from the branch directory to `.kd/backlog/tickets/`. The CLI could lie and the test would pass. Fix: assert source file removed and backlog file exists.

### LOW

**6. `FileNotFoundError` fallback lacks test coverage** (`src/kingdom/harness.py:712-718`)
The `add_message` call for council feedback is wrapped in `try/except FileNotFoundError`, but no test exercises this path. Fix: add a test that patches `add_message` to raise `FileNotFoundError` and verify graceful handling.

**7. `parse_verdict` regex doesn't tolerate markdown decoration** (`src/kingdom/harness.py:330`)
The regex requires `VERDICT: (APPROVED|BLOCKING)` as the entire line. If a council member wraps it in markdown (`**VERDICT: APPROVED**`), it won't match. Fallback is "assumed approved" per design, so this won't block, but it causes false "no verdict found" warnings. Fix: make the regex more permissive (strip common markdown chars before matching).

## Open Questions (King's Call)

**A. Should `review_bounce_count` reset on king reject?**
Currently the counter never resets — it accumulates across all review cycles including king-initiated rejects. If the king explicitly rejects and relaunches, should the counter start fresh? The design doc says "counter persisted in session state" but doesn't specify reset semantics.

**B. Should `get_diff` scope to latest iteration only?**
Currently `get_diff` uses `start_sha` (set once at session start) so after each council bounce the diff keeps growing and includes earlier rejected work. Scoping to the most recent iteration would give cleaner signal to council reviewers but loses cumulative context.

## Acceptance Criteria

- [ ] `--accept` validates feature branch before merging
- [ ] Hand-mode recovery instructions use correct path
- [ ] `--reject` checks harness liveness before relaunching
- [ ] Council feedback message asserted in harness test
- [ ] Backlog move test asserts file state, not just output
- [ ] `FileNotFoundError` fallback has test coverage
- [ ] `parse_verdict` regex tolerates markdown decoration
- [ ] King decides on bounce count reset and diff scope
