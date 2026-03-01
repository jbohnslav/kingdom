---
id: "fb7f"
status: closed
deps: []
links: [5b14]
created: 2026-03-01T02:01:14Z
type: task
priority: 2
closed_at: 2026-03-01T03:50:05Z
---
# Fix 5b14 implementation gaps: diff stat, first-iteration context, blocking feedback, and lossy agent summaries

Follow-up to 5b14 (Enrich harness worklog entries for real peasant observability). The core plumbing landed — council feedback collection, `summarize_feedback()`, multiline indentation — but code review by both claude and codex identified four concrete gaps where the implementation doesn't satisfy the ticket's acceptance criteria in practice.

## Issues

### 1. `get_diff_stat` is a no-op after agent commits (highest impact)

**Files:** `src/kingdom/harness.py:173-199`, called at ~line 680

**Problem:** `get_diff_stat()` runs `git diff --stat HEAD` (uncommitted vs HEAD) then `git diff --stat` (unstaged vs index). But the harness system prompt tells the agent to "commit your changes as you go." After the agent commits, both commands return empty — there's nothing uncommitted to diff. So the "Files changed:" worklog entry is silently missing for well-behaved agents, which is exactly the case this feature is meant to cover.

**Fix:** Capture HEAD before calling the agent, then after it returns, diff against that SHA:

```python
# Before agent call (~line 620):
pre_iteration_sha = subprocess.run(
    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=worktree
).stdout.strip()

# After agent returns (~line 680):
diff_stat = get_diff_stat(worktree, since=pre_iteration_sha)
```

Add a `since` parameter to `get_diff_stat` that runs `git diff --stat {since}..HEAD` instead of diffing the working tree.

### 2. First iteration is a blank entry (medium impact)

**Files:** `src/kingdom/harness.py:599`

**Problem:** Iteration 1 logs `Iteration 1/5 — calling agent` with zero context about what the peasant is working on. The King's prompt and ticket title are both available at this point but aren't included. The watch stream starts as a black box.

**Fix:** On the first iteration, include the ticket title (and optionally a truncated version of the prompt) in the worklog entry. The ticket object is already resolved at line 528.

### 3. Blocking reviews drop approving members' feedback (medium impact)

**Files:** `src/kingdom/harness.py:479-480`

**Problem:** `run_council_review()` collects `all_feedback` for both approved and blocking members, but when any member blocks, it returns only `blocking_feedback` (line 480). Approving members' reasoning is discarded. The watch output can't show each councillor's verdict on blocking runs, which misses the 5b14 acceptance criterion "each member's verdict AND their reasoning text."

**Fix:** Return `all_feedback` in both the approved and blocking cases. Keep `blocking_feedback` as a separate local variable only for the bounce message to the peasant (line 794), where you want to focus on what needs fixing.

### 4. `extract_worklog_entry` still produces useless agent summaries (required to finish 5b14, flagged by codex)

**Files:** `src/kingdom/harness.py:103`

**Problem:** `extract_worklog_entry()` takes the first paragraph before `STATUS:`. If the agent starts its response with `## What I did this iteration` followed by a blank line, the worklog entry is just that heading — everything useful below it is discarded. The flanking data (diff stat + council reasoning) helps, but the agent's own progress line remains a black box.

**Why this is in scope:** 5b14 still requires "Agent result entry includes a meaningful summary, not a placeholder heading." This follow-up should either fix that behavior or explicitly change the parent ticket. As written, treating it as optional leaves 5b14 internally inconsistent.

**Fix:** Make the agent-result entry meaningful in the current harness path. The lightest acceptable implementation is to skip standalone markdown headings / empty boilerplate when extracting the summary and use the next substantive paragraph instead. The cheap-model summarizer in backlog ticket `2f13` is still a valid later improvement, but it should not be required to close this ticket.

## Testing gaps

- `test_harness.py:326` only asserts generic "calling agent" output, not that iteration 1 includes context.
- `test_harness.py:1164` tests `get_diff_stat()` with mocked subprocess output but doesn't cover the committed-changes case that currently breaks the feature.
- No test asserts blocking reviews include approving members' verdicts/reasons in the worklog.
- No test asserts the agent-result worklog entry skips placeholder headings and surfaces substantive summary text.

## Acceptance Criteria

- [ ] `get_diff_stat` shows committed changes between iterations (not just uncommitted changes)
- [ ] First iteration worklog entry includes the ticket title / King's prompt
- [ ] Blocking council reviews include all members' verdicts in the worklog (not just blocking members)
- [ ] Agent summary entry is not a bare markdown heading with no content
- [ ] Tests cover: committed-change diff stat, first-iteration context, blocking review with mixed verdicts, and agent-result summary extraction
