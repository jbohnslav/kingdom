---
id: kin-02bf
status: open
deps: []
links: []
created: 2026-02-05T03:26:56Z
type: task
priority: 3
---
# Ticket discovery commands need clearer scoping

Currently `kd tk ready` mixes tickets from the current branch with backlog tickets, making it unclear what's actually relevant to the current work.

## Problem

Ticket discovery commands (`kd tk ready`, `kd tk list`) need clearer rules for which tickets they show:
- Current branch tickets
- Backlog tickets
- Other open branches' tickets

## Proposed Behavior

By default, show only current branch tickets. Add flags to expand scope:
- `--backlog` - include backlog tickets
- `--all` - include all locations (branches, backlog, maybe archive)

This matches the mental model: when working on a branch, focus on that branch's tickets. Explicitly opt-in to see broader context.

## Affected Commands

- `kd tk ready` - most important, used to find next work
- `kd tk list` - already has `--all` but behavior may need review
