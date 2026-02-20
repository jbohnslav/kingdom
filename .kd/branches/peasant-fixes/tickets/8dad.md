---
id: "8dad"
status: closed
deps: [bec3, 92ce]
links: []
created: 2026-02-17T17:31:36Z
type: task
priority: 2
---
# Harness council-review loop

## Description

After the peasant declares DONE and quality gates pass, automatically trigger a council review before escalating to the king.

Harness flow after gates pass:
1. Set ticket `in_review`, session `awaiting_council`
2. Fire council review prompt with diff (scoped by mode: `start_sha..HEAD` for hand, `<feature_branch>...HEAD` for worktree), worklog, and ticket description
3. Wait for council responses up to `cfg.council.timeout` (default 600s)
4. If timeout → session `needs_king_review`, exit with partial reviews
5. Persist council responses to work thread, parse `VERDICT: APPROVED|BLOCKING` final lines
6. If any BLOCKING and `review_bounce_count < 3`: append feedback as directives, ticket → `in_progress`, session → `working`, increment bounce count, resume loop
7. If all APPROVED or bounce count >= 3: session → `needs_king_review`, exit

Council review prompt protocol: free-form review body + required final line `VERDICT: APPROVED` or `VERDICT: BLOCKING`. Missing verdict = assumed APPROVED (log warning).

## Acceptance Criteria

- [ ] Harness triggers council review after quality gates pass
- [ ] Council review prompt includes diff, worklog, and ticket description
- [ ] Diff scoped correctly for hand mode vs worktree mode
- [ ] `VERDICT:` lines parsed from council responses
- [ ] Blocking verdicts send peasant back to `working` with feedback
- [ ] `review_bounce_count` incremented and persisted on each bounce
- [ ] Escalates to `needs_king_review` after 3 bounces
- [ ] Council timeout triggers escalation with partial responses
- [ ] Tests pass
