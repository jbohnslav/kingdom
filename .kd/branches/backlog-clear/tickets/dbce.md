---
id: "dbce"
status: closed
deps: []
links: []
created: 2026-02-14T19:51:53Z
type: task
priority: 2
---
# Agent skill wording is too strong — codex thought it was modifying state

## Context

When codex was asked to review the branch via `kd council ask`, it interpreted
the skill's imperative "Working Tickets" instructions ("start a ticket, do the
work, close it") as directives to actually execute. It began running state-
modifying `kd` commands (creating files, checking status) as if it were a
worker, rather than treating the skill as reference documentation.

The root cause is that the skill reads like a runbook for the active agent. An
agent asked to "review" still sees "One at a time: start a ticket, do the work,
close it" and may interpret that as what it should do right now.

## Fix

Soften the imperative language in `skills/kingdom/SKILL.md` so agents
understand the skill is a reference guide, not a set of commands to execute
immediately. Options:

1. Add a framing paragraph at the top: "This document describes the kd workflow
   for reference. Only run commands when the King asks you to — do not
   autonomously modify project state."
2. Reword the "Working Tickets" section from imperative ("start a ticket") to
   descriptive ("the workflow is to start a ticket…").
3. Both.

## Acceptance Criteria

- [ ] Skill includes explicit guidance that agents should not autonomously run
      state-modifying kd commands unless directed by the King
- [ ] "Working Tickets" section uses descriptive rather than imperative language
- [ ] A read-only agent (e.g. council reviewer) would not interpret the skill as
      instructions to modify state
