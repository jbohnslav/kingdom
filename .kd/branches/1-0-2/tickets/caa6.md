---
id: "caa6"
status: open
deps: []
links: []
created: 2026-09-05T18:49:50Z
type: task
priority: 2
---
# Scope Kingdom skill discovery to context changes

From the 2026-09-02 Kingdom skill feedback: every-turn wording triggers redundant status/list calls. Rename the heading to Run When Resolving or Changing Context, discover once per new request or branch/ownership change, and skip routine resolved-ticket follow-ups. Explicitly reserve uv run kd for Kingdom source and use installed kd everywhere else, including Python/uv projects.

## Acceptance Criteria

- [ ] Skill clearly scopes discovery and CLI invocation as requested
- [ ] Skill references remain consistent and full test suite passes
