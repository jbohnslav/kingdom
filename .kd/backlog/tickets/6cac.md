---
id: 6cac
status: closed
deps: []
links: []
created: 2026-02-13T18:07:05Z
type: bug
priority: 2
---
# Empty branch name from normalization

normalize_branch_name() can return empty string for non-ASCII input, causing state to write to .kd/branches/ root. Add guard for empty result. (state.py:26-60, #8 from PR #6 review)
