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

**2. Hand-mode peasant review is fundamentally broken** (`src/kingdom/cli.py:2246, 2310`)
`--accept` always merges `ticket/<id>` branch, but hand mode (`kd peasant start --hand`) does not create a ticket branch or worktree — it works directly in the main worktree. So `--accept` fails (missing branch) and `--reject` auto-resume fails (missing worktree path at `.kd/worktrees/<id>`). The original finding #2 (wrong recovery instructions) is a symptom of this deeper problem. Fix: detect hand-mode in both accept and reject flows and handle accordingly (e.g., accept in hand mode means changes are already on the feature branch; reject in hand mode should relaunch in-place).

### MEDIUM

**3. `--reject` always relaunches harness, risking duplicate workers** (`src/kingdom/cli.py:2278-2328`)
The new reject flow unconditionally spawns `kd work` without checking whether the previous harness is still alive. Two concurrent harnesses on the same worktree will race over files and logs. Fix: gate reject/resume on session phase (`needs_king_review`) and hand/worktree mode rather than pure `os.kill(pid, 0)` liveness (note: the test suite explicitly codifies stale-PID relaunch semantics at `tests/test_cli_peasant.py:973`, so a naive PID liveness check would regress that case).

**4. Council-block feedback message not asserted in tests** (`tests/test_harness.py:1248-1273`)
`test_council_blocking_bounces_back` checks `review_bounce_count` and final status but never verifies that the `## Council Review Feedback (BLOCKING)` message was actually written to the work thread via `add_message`. A regression that breaks feedback delivery would pass this test silently. Fix: assert `add_message` was called with expected content, or check the thread file.

**5. Backlog move test checks output text, not file state** (`tests/test_cli_ticket.py:536-547`)
`test_move_to_backlog_shows_backlog_label` asserts CLI output says "Moved ... to backlog" but never checks that the ticket file actually moved from the branch directory to `.kd/backlog/tickets/`. The CLI could lie and the test would pass. Fix: assert source file removed and backlog file exists.

### LOW

**6. Worktree diff mode doesn't match design** (`src/kingdom/harness.py:248`, `.kd/branches/peasant-fixes/design.md:134`)
Design doc specifies worktree mode should use `<feature>...HEAD` (three-dot merge-base diff), but `get_diff` always uses `start_sha..HEAD` (two-dot). For worktree mode this may include parent branch changes, producing noisier diffs for council review. Fix: use three-dot form for worktree-mode peasants as the design intended.

**7. `FileNotFoundError` fallback lacks test coverage** (`src/kingdom/harness.py:712-718`)
The `add_message` call for council feedback is wrapped in `try/except FileNotFoundError`, but no test exercises this path. Fix: add a test that patches `add_message` to raise `FileNotFoundError` and verify graceful handling.

**8. `parse_verdict` regex doesn't tolerate markdown decoration** (`src/kingdom/harness.py:330`)
The regex requires `VERDICT: (APPROVED|BLOCKING)` as the entire line. If a council member wraps it in markdown (`**VERDICT: APPROVED**`), it won't match. Fallback is "assumed approved" per design, so this won't block, but it causes false "no verdict found" warnings. Fix: make the regex more permissive (strip common markdown chars before matching).

## Open Questions (King's Call)

**A. Should `review_bounce_count` reset on king reject?**
Currently the counter never resets — it accumulates across all review cycles including king-initiated rejects. If the king explicitly rejects and relaunches, should the counter start fresh? The design doc says "counter persisted in session state" but doesn't specify reset semantics.


## Acceptance Criteria

- [ ] `--accept` validates feature branch before merging
- [ ] Hand-mode accept and reject flows work correctly (no missing branch/worktree)
- [ ] `--reject` gates relaunch on session phase and mode, not just PID liveness
- [ ] Council feedback message asserted in harness test
- [ ] Backlog move test asserts file state, not just output
- [ ] Worktree-mode diff uses three-dot merge-base form per design
- [ ] `FileNotFoundError` fallback has test coverage
- [ ] `parse_verdict` regex tolerates markdown decoration
- [ ] King decides on bounce count reset and diff scope
