---
id: "caa6"
status: closed
deps: []
links: []
created: 2026-09-05T18:49:50Z
type: task
priority: 2
closed_at: 2026-09-05T19:01:57Z
resolution: completed
close_reason: "Scoped context discovery and clarified checkout-only uv invocation; skill copies current and full suite passes"
closed_context: codex:1fd7693df963292c
assignee: codex:1fd7693df963292c
---
# Scope Kingdom skill discovery to context changes

From the 2026-09-02 Kingdom skill feedback: every-turn wording triggers redundant status/list calls. Rename the heading to Run When Resolving or Changing Context, discover once per new request or branch/ownership change, and skip routine resolved-ticket follow-ups. Explicitly reserve uv run kd for Kingdom source and use installed kd everywhere else, including Python/uv projects.

## Acceptance Criteria

- [x] Skill clearly scopes discovery and CLI invocation as requested
- [x] Skill references remain consistent and full test suite passes

## Worklog

- [2026-09-05 15:00] [codex:1fd7693d] — Applied the report's suggested discovery cadence and heading, retained the durable ticket-update workflow, and made the command distinction explicit: uv run kd only in Kingdom source; installed kd in every other repository, including Python/uv projects. Updated the ticket reference to avoid contradicting that cadence. This is a wording correction; no new tests that merely assert strings are added. Existing skill-schema, link, packaging-mirror, and full-suite checks cover structural consistency.
- [2026-09-05 15:01] [codex:1fd7693d] — Verified the final skill and ticket-reference wording against the report and reviewed existing links and packaged mirrors. Full suite passed: 2338 passed, 49 skipped, 1 xfailed; git diff --check passed. The generic skill validator's unsupported pre-existing compatibility key is documented in 5514; Kingdom's schema tests pass. Refreshed through the existing install_skill helper (without upgrading the released CLI): Claude and Codex managed copies already matched the working-tree bundle; Cursor is not configured. All acceptance criteria complete.
- [15:01] [codex:1fd7693df963292c] — Closed: Scoped context discovery and clarified checkout-only uv invocation; skill copies current and full suite passes

## Lifecycle

- 2026-09-05T19:01:57Z [codex:1fd7693df963292c] — closed (completed): Scoped context discovery and clarified checkout-only uv invocation; skill copies current and full suite passes
