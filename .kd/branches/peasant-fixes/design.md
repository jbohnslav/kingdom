# Design: peasant-fixes

## Goal

Harden the peasant workflow into a proper RALPH loop with an explicit review phase, council-driven code review, and clear state visibility — so peasants self-correct on councillor feedback before escalating to the king.

## Context

The peasant harness (`harness.py`) already has most of a RALPH loop:
- Iterative prompt→agent→parse-status→repeat cycle with `STATUS: CONTINUE|BLOCKED|DONE`
- Quality gates (pytest + ruff) that reject `DONE` back to `CONTINUE`
- King→peasant directives via work thread messages
- Session state tracking (`working`, `blocked`, `done`, `failed`, `stopped`)

What's missing:
- **No review phase.** When the peasant passes quality gates, it goes straight to `done`. The king has to manually check work and run `kd peasant review`. There's no signal that work is ready for review.
- **No council review.** Councillors never see peasant output unless the king manually runs `kd council ask`. The peasant can't self-correct on design feedback.
- **No diff scoping.** No record of where the peasant started, so there's no clean way to generate a diff of just the peasant's work.
- **Implicit review state.** When the peasant declares DONE and gates pass, the session says `done` but the ticket is still `open` — the "awaiting review" state is invisible.

## Requirements

1. **Add `in_review` ticket status.** Ticket lifecycle becomes: `open → in_progress → in_review → closed`. Visible on the board, signals implementation complete and awaiting review.
   Transition rules: move `open → in_progress` on `kd peasant start`; also force `in_progress` on `kd peasant review --reject`.
2. **Add session sub-states for the review phase.** New statuses: `awaiting_council` (council review dispatched, waiting for responses) and `needs_king_review` (council approved or escalated, king must act).
3. **Council auto-review on peasant DONE.** When the peasant passes quality gates, automatically fire a council review prompt with the diff, worklog, and ticket description. Councillors respond with free-form review plus a `VERDICT: APPROVED|BLOCKING` final line. If blocking, peasant resumes work with feedback. If approved, escalate to king.
4. **Council review bounce limit (persistent).** After 3 council rejection cycles on the same ticket, escalate to `needs_king_review` with full feedback history. Persist `review_bounce_count` in session state so restarts don't reset it.
5. **Council timeout policy.** `awaiting_council` uses `cfg.council.timeout` (default `600s`). On timeout, transition to `needs_king_review` with partial council responses.
6. **CLI compatibility for `in_review`.** Update all commands that reference ticket status to handle the new state correctly.
7. **`kd peasant review` updates.** `--accept` closes ticket + session `done`. `--reject "feedback"` returns ticket to `in_progress` + session `working` and auto-resumes the peasant (with `--no-resume` opt-out).
8. **Persist `start_sha` in session state.** Record the commit SHA when the peasant begins work. Diff scope rules:
   - Hand/single-worktree mode: `start_sha..HEAD`
   - Worktree mode: `<feature_branch>...HEAD`

## Non-Goals

- **Notification subsystem.** No file-backed alert queue in v1. The board (`kd tk list`, `kd status`) is the notification — `in_review` is visible there. Add notifications later if pull-based proves insufficient.
- **Event-driven auto-resume for blocked peasants.** Blocked peasant = exited process. Manual relaunch when blockers resolve.
- **Daemon or watcher process.** Everything stays file-based and poll-based.
- **Changes to the Hand.** Council TUI is the primary interaction surface now.

## Design

### State Model

**Ticket statuses** (file-level, visible on board):
```
open → in_progress → in_review → closed
```

**Session statuses** (runtime, visible in `kd peasant status`):
```
idle → working → awaiting_council → needs_king_review → done
                ↘ blocked                                ↗
                ↘ failed                                ↗
                ↘ stopped                               ↗
```

Ticket status = what phase the work is in. Session status = what the agent is doing right now. `in_review` on the ticket means "implementation complete, under review." `awaiting_council` vs `needs_king_review` on the session tells you where in that review process.

### Harness Flow (Updated)

```
1. If ticket is `open`, set it to `in_progress`. Record `start_sha` if not already set in session state.
2. Build prompt → call agent → parse response → append worklog.
3. If STATUS: CONTINUE → loop (step 2).
4. If STATUS: BLOCKED → session "blocked", ticket stays "in_progress", exit.
5. If STATUS: DONE →
   a. Run quality gates (pytest + ruff).
   b. If gates fail → back to step 2 (existing behavior).
   c. If gates pass →
      i.   Set ticket "in_review", session "awaiting_council".
      ii.  Fire council review prompt (diff scoped by mode + worklog + ticket).
      iii. Wait for council responses (up to `cfg.council.timeout`, default 600s).
      iv.  If timeout → session "needs_king_review", exit with partial reviews.
      v.   Persist each council response to the ticket work thread, then parse VERDICT lines.
      vi.  If any BLOCKING and review_bounce_count < 3:
             - Append feedback as directives to thread.
             - Set ticket "in_progress", session "working".
             - Increment review_bounce_count (persisted in session).
             - Back to step 2.
      vii. If all APPROVED or review_bounce_count >= 3:
             - Set session "needs_king_review".
             - Exit harness.
6. Max iterations → session "failed", exit.
```

### Council Review Protocol

The harness invokes council review directly (in-process, not subprocess). The review prompt includes:
- Ticket title and description
- The diff:
  - Hand/single-worktree mode: `git diff <start_sha>..HEAD`
  - Worktree mode: `git diff <feature_branch>...HEAD`
- The worklog (iteration history)
- Instruction: review the implementation, flag issues, respond with free-form analysis followed by a final line: `VERDICT: APPROVED` or `VERDICT: BLOCKING`

Persistence + parsing:
- Persist each councillor response into the ticket work thread (or a dedicated per-ticket review thread), then write one king-facing summary directive for the peasant.
- Scan each councillor's response for the last line matching `VERDICT: (APPROVED|BLOCKING)`. If no verdict line found, treat as `APPROVED` (don't block on format errors — log a warning).

### Session State Additions

New fields on `AgentState`:
- `start_sha: str | None` — commit SHA when peasant started work
- `review_bounce_count: int` — number of council rejection cycles (default 0)

These are persisted to session JSON on disk, surviving process restarts.

### CLI Compatibility Matrix (`in_review`)

| Command | Behavior with `in_review` |
|---|---|
| `kd status` | Include `in_review` as its own count bucket |
| `kd tk list` | Display `in_review` tickets; accept `--status in_review` filter |
| `kd tk current` | Returns `in_progress` tickets only (exclude `in_review`) |
| `kd tk ready` | Excludes `in_review` (not dispatchable) |
| `kd peasant review` | Valid only when ticket is `in_review` |
| `kd peasant start` | If ticket is `open`, set to `in_progress`; cannot start on `in_review` (must reject or accept first) |

### `kd peasant review` Flow

```
kd peasant review <ticket>                      # Show review info (diff, worklog, council feedback)
kd peasant review <ticket> --accept             # Close ticket, session → done
kd peasant review <ticket> --reject "feedback"  # Ticket → in_progress, session → working, auto-resume
kd peasant review <ticket> --reject --no-resume # Same but don't relaunch peasant
```

## Decisions

- **`in_review` is a ticket status, not just session-level.** It's visible on the board when you run `kd tk list`, which is the primary way the king sees what's going on. Session sub-states (`awaiting_council`, `needs_king_review`) provide granularity within that phase.
- **Council verdict protocol: structured final line.** Free-form review body + required `VERDICT: APPROVED|BLOCKING` as the last line. Matches the `STATUS:` pattern already used in the peasant loop. Missing verdict = assumed approved (don't block on format issues).
- **Diff scope is mode-dependent.** Hand/single-worktree uses `start_sha..HEAD`. Worktree mode uses `<feature_branch>...HEAD` to avoid parent-branch noise.
- **`--reject` auto-resumes by default.** RALPH-consistent: if you're giving feedback, you want the peasant to act on it. `--no-resume` is the opt-out for when you want manual control.
- **Bounce limit of 3, hardcoded.** If the peasant bounces between working and council review 3 times, something is fundamentally wrong. Escalate to king rather than spin. Counter persisted in session state. Can be made configurable later if needed.
- **Council timeout comes from `cfg.council.timeout`.** Default 600s. On timeout, escalate to `needs_king_review` with whatever partial responses arrived.
- **No notification subsystem in v1.** The board is the notification. `kd tk list` shows `in_review` status. Add a notification queue later if this proves insufficient in practice.
- **No daemon.** File-based, poll-based. Peasant exits when it reaches a terminal state. King checks the board.

## Open Questions

- **Council review prompt format details.** Exact wording of the review instruction. How much of the worklog to include (full history vs last N iterations)?
- **Handling councillor disagreement.** If 2 say APPROVED and 1 says BLOCKING, is that blocking? Current design: any BLOCKING = blocking. Could be majority-rules instead.

## Ticket Breakdown

1. **`in_review` ticket status + CLI compatibility.** Add status to ticket model, update `kd status`, `kd tk list`, `kd tk current`, `kd tk ready`, `kd peasant start` guards.
2. **Session state additions.** Add `awaiting_council`, `needs_king_review` to `AGENT_STATUSES`. Add `start_sha` and `review_bounce_count` fields to `AgentState`. Persist to session JSON.
3. **Harness council-review loop.** After quality gates pass: fire council review, parse `VERDICT:` lines, handle timeout, bounce logic, state transitions.
4. **`kd peasant review` accept/reject UX.** `--accept` closes ticket. `--reject` writes feedback + auto-resumes (with `--no-resume` opt-out). Show review info (diff, worklog, council feedback).
