---
id: "bdbf"
status: in_progress
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
`peasant review --accept` runs `git merge ticket/<id>` from the base repo but never validates or switches to the feature branch recorded in `.kd/current`. The merge target is whatever branch the user happens to have checked out. This can silently merge peasant work into the wrong branch (e.g., `main`). Fix: hard-fail if current branch != feature branch from `.kd/current`. Do not auto-switch — that's a hidden side effect. Error message: "Cannot accept: expected to be on {feature} but HEAD is on {current}. Switch branches and retry."

**2. Hand-mode peasant review is fundamentally broken** (`src/kingdom/cli.py:2246, 2310`)
`--accept` always merges `ticket/<id>` branch, but hand mode (`kd peasant start --hand`) does not create a ticket branch or worktree — it works directly in the main worktree. So `--accept` fails (missing branch) and `--reject` auto-resume fails (missing worktree path at `.kd/worktrees/<id>`). The original finding #2 (wrong recovery instructions) is a symptom of this deeper problem.

Fix decisions:
- **Detection:** Add `hand_mode: bool` field to `AgentState` (persisted in session state). Set it when `peasant start --hand` launches. Do not infer from worktree existence — that's fragile.
- **Accept in hand mode:** Skip the merge entirely — changes are already on the feature branch. Close the ticket and mark done. Trust-based: king's `--accept` is an assertion.
- **Reject in hand mode:** Relaunch in-place (pass base repo as working dir, not worktree). Replicate the `list_active_agents` collision guard from `peasant start --hand` to prevent concurrent hand-mode peasants.
- **Review UI diff in hand mode:** The review diff display (`src/kingdom/cli.py:2377`) uses `HEAD...ticket/<id>` which is broken for hand mode. Fix to use appropriate diff for hand-mode tickets.

### MEDIUM

**3. `--reject` always relaunches harness, risking duplicate workers** (`src/kingdom/cli.py:2278-2328`)
The new reject flow unconditionally spawns `kd work` without checking whether the previous harness is still alive. Two concurrent harnesses on the same worktree will race over files and logs.

Fix decisions:
- Require `state.status == "needs_king_review"` before allowing `--reject` (not just ticket status).
- Before relaunching, verify the old PID is dead. If alive, refuse with a clear error.
- The stale-PID test at `tests/test_cli_peasant.py:973` covers `peasant start`, not `peasant review --reject` — these are separate code paths, no conflict.
- For hand-mode reject, use base repo dir (not worktree) and apply collision guard per Finding 2.

**4. Council-block feedback message not asserted in tests** (`tests/test_harness.py:1248-1273`)
`test_council_blocking_bounces_back` checks `review_bounce_count` and final status but never verifies that the `## Council Review Feedback (BLOCKING)` message was actually written to the work thread via `add_message`. A regression that breaks feedback delivery would pass this test silently. Fix: assert `add_message` was called with expected content, or check the thread file.

**5. Backlog move test checks output text, not file state** (`tests/test_cli_ticket.py:536-547`)
`test_move_to_backlog_shows_backlog_label` asserts CLI output says "Moved ... to backlog" but never checks that the ticket file actually moved from the branch directory to `.kd/backlog/tickets/`. The CLI could lie and the test would pass. Fix: assert source file removed and backlog file exists.

### LOW

**6. Worktree diff mode doesn't match design** (`src/kingdom/harness.py:248`, `.kd/branches/peasant-fixes/design.md:134`)
Design doc specifies worktree mode should use `<feature>...HEAD` (three-dot merge-base diff), but `get_diff` always uses `start_sha..HEAD` (two-dot). For worktree mode this may include parent branch changes, producing noisier diffs for council review. This is a real issue — multiple peasants work in parallel and the feature branch advances, so two-dot picks up other peasants' changes. Fix: pass feature branch name into `get_diff` for worktree-mode peasants and use three-dot form. Add fallback behavior if the ref is missing/detached.

**7. `FileNotFoundError` fallback lacks test coverage** (`src/kingdom/harness.py:712-718`)
The `add_message` call for council feedback is wrapped in `try/except FileNotFoundError`, but no test exercises this path. Fix: add a test that patches `add_message` to raise `FileNotFoundError` and verify graceful handling.

**8. `parse_verdict` regex doesn't tolerate markdown decoration** (`src/kingdom/harness.py:330`)
The regex requires `VERDICT: (APPROVED|BLOCKING)` as the entire line. If a council member wraps it in markdown (`**VERDICT: APPROVED**`), it won't match. Fallback is "assumed approved" per design, so this won't block, but it causes false "no verdict found" warnings.

Fix: strip `*`, `_`, `` ` ``, and leading `>`, `-`, `#` from each line before matching. Also update the "has verdict line" warning check (`src/kingdom/harness.py:402`) to use the same stripping — otherwise false warnings remain even after the parser is fixed.

## Resolved Questions

**A. `review_bounce_count` resets on king reject.**
A king reject is an explicit "start over" signal, so the counter resets to 0 when the king rejects and relaunches. This gives the peasant a fresh set of council review cycles for the new attempt.

## Acceptance Criteria

- [ ] `--accept` hard-fails if HEAD branch != feature branch
- [ ] `hand_mode` field added to `AgentState` and persisted in session state
- [ ] Hand-mode accept skips merge, closes ticket directly
- [ ] Hand-mode reject relaunches in-place with collision guard
- [ ] Hand-mode review UI diff works correctly (no broken `ticket/<id>` ref)
- [ ] `--reject` requires `state.status == "needs_king_review"`
- [ ] `--reject` verifies old PID is dead before relaunching
- [ ] `--reject` resets `review_bounce_count` to 0
- [ ] Council feedback message asserted in harness test (all bounce iterations)
- [ ] Backlog move test asserts file state, not just output
- [ ] Worktree-mode diff uses three-dot merge-base form with feature branch ref
- [ ] `FileNotFoundError` fallback has test coverage
- [ ] `parse_verdict` strips markdown decoration before matching
- [ ] "Has verdict line" warning check also strips markdown decoration
