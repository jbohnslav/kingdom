---
from: codex
to: king
timestamp: 2026-02-09T15:46:35Z
---

I’m going to read the smoke test worklog and current `design.md`, extract concrete failure patterns, then propose a focused v2 design that addresses each gap you listed with explicit workflow and quality gates.
I found the worklog; next I’ll locate the right `design.md` in the repo and read both files to build the v2 proposal against actual findings.
I’ve extracted the concrete pain points from the worklog; now I’m reading the active branch design doc so the v2 proposal maps directly to existing sections and terminology.
I have enough context to draft v2; I’m pulling exact line references from the worklog and design so the proposal is concrete and easy to apply section-by-section.
`design.md` v2 should tighten the runtime contract around what the smoke test exposed, not add new architecture.

Key evidence from the worklog:
- Harness/review mismatch on gates: `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:111`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:113`
- Missing worktree bootstrap (`uv sync`, pre-commit): `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:108`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:109`
- Poor logs: `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:102`, `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:107`
- Reject does not relaunch: `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:110`
- Worktree staleness: `.kd/branches/refactor-multi-agent/tickets/kin-41f9.md:106`

Current design sections that need replacement/expansion:
- `.kd/branches/refactor-multi-agent/design.md:312`
- `.kd/branches/refactor-multi-agent/design.md:314`
- `.kd/branches/refactor-multi-agent/design.md:395`
- `.kd/branches/refactor-multi-agent/design.md:414`

## Proposed v2 shape

### 1. Unified Quality Gate Contract
Define one shared gate function used by both harness and `kd peasant review`:

1. `uv run pytest`
2. `uv run ruff check`
3. `uv run ruff format --check` (or `uv run pre-commit run --all-files` if pre-commit is canonical)

Rules:
- Peasant cannot transition to `done` unless all gates pass.
- `review` must call the same gate runner, not a different command set.
- Gate failure writes full command, exit code, and last N lines of output to logs and thread message.

### 2. Deterministic Worktree Bootstrap
Before first harness iteration (and before review), run bootstrap in worktree:

1. `uv sync`
2. `uv run pre-commit install` (with hooks installed)

Persist `bootstrap.json` in session metadata with:
- `synced_at`, `precommit_installed_at`, `python_version`, `uv_lock_hash`

If bootstrap fails, set status `blocked` with actionable error.

### 3. Peasant Log Visibility
`kd peasant logs --follow` should show:
- Iteration header
- Prompt summary (ticket/directives hash, not full private content)
- Backend command + exit status
- Files changed summary
- Quality gate results with failing output snippet

Add per-iteration log files under `logs/peasant-<ticket>/iterations/<n>.log` and keep stdout/stderr raw logs.

### 4. Reject/Relaunch Workflow
`kd peasant review --reject "..."` must be atomic:

1. Append feedback directive to thread
2. If harness not alive, relaunch automatically
3. Update session status to `working` with new PID

Add explicit `kd peasant restart <ticket>` alias for manual control.
Add `kd peasant msg --wake` to relaunch if message is sent to a dead peasant.

### 5. Worktree Staleness Policy
Track `base_commit` at worktree creation. On every `start/restart/review`:

- Compare worktree base to current parent branch head.
- If stale and worktree clean: fast-forward/rebase automatically.
- If stale and dirty: fail loudly with required action (`--restack` / manual resolve).
- Show staleness in `kd peasant status` (`fresh|stale` + commit distance).

This prevents running old tests/code and fixes the “DONE but stale failures” loop.

## Ticket-level v2 breakdown changes
- Expand T5 acceptance to include bootstrap + unified gates + detailed logs + staleness check.
- Expand T6 acceptance to include reject auto-relaunch + `msg --wake`.
- Add T7 “Worktree freshness and bootstrap invariants” if you want this isolated.

If you want, I can draft the exact replacement text for those sections in `.kd/branches/refactor-multi-agent/design.md` as a ready-to-apply patch.
