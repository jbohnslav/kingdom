---
id: "d4fc"
status: open
deps: []
links: []
created: 2026-02-27T13:24:39Z
type: task
priority: 1
---
# Claude Code hooks plugin: auto-append to work log after every agent turn

## Problem

Work logs should be a running narrative of what happened — "user asked X, I investigated Y, found Z." But right now you have to manually prompt the agent to update the work log every time. It should be automatic.

Claude Code supports hooks that fire on events like `stop` (after every assistant turn before waiting for user input). A kingdom hooks plugin could detect the current ticket context and auto-append a summary to the work log after each meaningful turn.

## Ideas

- Use Claude Code's `hooks` system (e.g. `stop` or `notification` events) to trigger a `kd tk add-note` after each turn
- The hook could use a small/fast model to summarize what just happened into a one-liner for the work log
- Should be smart enough to skip no-op turns (e.g. just answering a clarifying question with no code changes)
- Could also auto-log ticket status changes, file edits, test runs

## Acceptance Criteria

- [ ] Claude Code hooks plugin exists (e.g. `.claude/hooks/` or settings.json config) that integrates with kd
- [ ] After each meaningful agent turn, a summary is auto-appended to the current ticket's work log
- [ ] Trivial turns (no code changes, no research) are skipped
- [ ] Plugin can be disabled or configured
