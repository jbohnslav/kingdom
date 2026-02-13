# Design: cli-output-cleanup

## Goal
Make all kd CLI output cleaner, more parseable by agents, and easier to copy-paste for humans. Remove visual noise (Rich panels, box-drawing chars) and fix small UX papercuts in output formatting.

## Context
The CLI currently uses Rich `Panel` widgets in 11 places — council responses, peasant logs, test results, diffs, worklogs. These bordered boxes (`╭──╮`) look nice but:
- Break copy-paste (box chars get included)
- Are hard for agents to parse
- Add visual noise that obscures the actual content
- Create weird line breaks on narrow terminals

Additionally, several small output issues compound into friction:
- `kd design` prints absolute paths (agents try to use `/Users/jrb/...` instead of relative)
- `kd tk show` doesn't display the ticket file path (agents can't reference it)
- `kd status` could be more informative
- "runs" terminology lingers in help text and error messages
- Council worker doesn't strip trailing whitespace, causing pre-commit hook failures

## Requirements
- Replace all Rich `Panel` usage with plain markdown rendering or simple text
- `kd design` prints repo-relative paths
- `kd tk show` displays file path at top of output
- Remove "runs" terminology from user-facing strings
- Council worker strips trailing whitespace from messages
- `kd tk move` defaults to current branch when no branch arg given
- Rich tables (e.g. `kd peasant status`) are fine — only panels need to go

## Non-Goals
- Changing ticket ID format (kin-98e7 is a separate effort)
- Adding @mentions (kin-09c9 is a separate effort)
- Ticket assignment system (kin-b76b is a separate effort)
- Council timeout/async changes (separate PR)
- Branch protection (GitHub config, not code)

## Decisions
- **Plain markdown over Rich Markdown renderer**: Use `typer.echo()` with plain text rather than `console.print(Markdown(...))`. Agents and terminals handle plain text better than ANSI-colored markdown. For council responses and long content, print the raw markdown text directly — most terminals and agents render it fine.
- **Section headers instead of panels**: Replace panels with simple `--- header ---` or `## header` style separators. Keep it minimal.
- **Relative paths everywhere**: Use `Path.relative_to(base)` or manual relative path construction for all displayed paths.

## Open Questions
- Should we keep Rich `Console` at all, or go fully plain `typer.echo`? Leaning toward keeping Console only for tables.

## Work Log
(Appending notes on the kd workflow experience as work progresses)

### Session Start
- `git checkout -b cli-output-cleanup` + `kd start` was smooth — two commands to get going.
- `kd design` created the template. It printed the absolute path `/Users/jrb/code/kingdom/.kd/branches/cli-output-cleanup/design.md` — exactly the bug we're fixing.
- Explored the codebase to understand Panel usage patterns before writing this doc. Found 11 Panel instances in cli.py, all following a similar pattern.
- `kd tk ready` gives a nice overview of available work. The ticket format `kin-XXXX [P#][status] - title` is readable.
