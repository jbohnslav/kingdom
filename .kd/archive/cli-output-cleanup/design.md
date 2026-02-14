# Design: cli-output-cleanup

## Goal
Make all kd CLI output cleaner, more parseable by agents, and easier to copy-paste for humans. Remove visual noise (Rich panels, box-drawing chars) and fix small UX papercuts in output formatting.

## Context
The CLI currently uses Rich `Panel` widgets in 11 places — council responses, peasant logs, test results, diffs, worklogs. These bordered boxes (`╭──╮`) look nice but:
- Break copy-paste (box chars get included)
- Are hard for agents to parse (box-drawing chars pollute LLM context windows)
- Add visual noise that obscures the actual content
- Create weird line breaks on narrow terminals

The Rich `Markdown` renderer itself is fine — it produces nicely formatted output with bold, syntax-highlighted code blocks, etc. The problem is specifically the `Panel` wrapper adding borders around everything.

Additionally, several small output issues compound into friction:
- `kd design` prints absolute paths (agents try to use `/Users/jrb/...` instead of relative)
- `kd tk show` doesn't display the ticket file path (agents can't reference it)
- `kd status` could be more informative
- "runs" terminology lingers in help text and error messages
- Council worker doesn't strip trailing whitespace, causing pre-commit hook failures

## Requirements
- Replace all Rich `Panel` usage with `## header` + `Markdown()` rendering (no boxes)
- `kd design` prints repo-relative paths
- `kd tk show` displays file path at top of output
- Remove "runs" terminology from user-facing strings
- Council strips trailing whitespace from messages at write-time (all paths, not just worker)
- `kd tk move` defaults to current branch when no branch arg given
- Rich tables (e.g. `kd peasant status`), progress spinners, and `Markdown` renderer are all fine — only `Panel` needs to go

## Non-Goals
- Changing ticket ID format (kin-98e7 is a separate effort)
- Adding @mentions (kin-09c9 is a separate effort)
- Ticket assignment system (kin-b76b is a separate effort)
- Council timeout/async changes (separate PR)
- Branch protection (GitHub config, not code)

## Decisions
- **Keep Rich Markdown, drop Panel**: Use `console.print(Markdown(content))` directly instead of wrapping in `Panel(Markdown(content), ...)`. The Markdown renderer gives nice formatted output (bold, code highlighting, etc.) without the box-drawing noise. Prepend a `## header` to the content string so sections are visually separated.
- **Pattern for replacing panels**: Instead of `console.print(Panel(Markdown(body), title="claude", border_style="blue"))`, do `console.print(Markdown(f"## claude\n\n{body}"))`. Clean, parseable, no box chars.
- **Keep Rich Console**: Console stays for Markdown rendering, Tables, and Progress spinners. Only Panel import gets removed.
- **`## header` separators**: Use markdown H2 headers as section dividers (not `--- header ---`). Agents parse these correctly as section boundaries.
- **Relative paths everywhere**: Use `Path.relative_to(base)` for all displayed paths.
- **Strip whitespace at write-time**: Fix trailing whitespace in all council write paths (worker.py, council.py, cli.py), not just display-time, so `.kd/` files are clean for pre-commit hooks.
- **tk move default branch**: When no target branch given, default to `resolve_current_run(base)`. Handle the case where ticket is already on the target branch gracefully.

## Scope Notes (from council review)
- Also update `doctor()` which uses `console.print()` with Rich markup — can simplify to `typer.echo()`.
- "Runs" terminology changes will require updating test assertions (tests/test_cli_council.py, tests/test_done.py, tests/test_cli_ticket.py).
- Trailing whitespace stripping should cover sync council writes too (council.py:115, cli.py:388), not just the async worker path.

## Work Log
(Appending notes on the kd workflow experience as work progresses)

### Session Start
- `git checkout -b cli-output-cleanup` + `kd start` was smooth — two commands to get going.
- `kd design` created the template. It printed the absolute path `/Users/jrb/code/kingdom/.kd/branches/cli-output-cleanup/design.md` — exactly the bug we're fixing.
- Explored the codebase to understand Panel usage patterns before writing this doc. Found 11 Panel instances in cli.py, all following a similar pattern.
- `kd tk ready` gives a nice overview of available work. The ticket format `kin-XXXX [P#][status] - title` is readable.
- `kd tk move` requires explicit branch target — experienced the exact bug from kin-3f60 firsthand.
- Council review was useful. All three members agreed: keep Rich for Tables/Spinners/Markdown, drop Panel. Codex flagged that trailing whitespace stripping needs to cover all write paths, not just the worker.
- Pre-commit hook caught trailing whitespace in a council response file — exactly the bug kin-4096 describes. Had to re-stage and re-commit.

### Council Feedback (round 1)
- Consensus: keep Rich Console for Tables, Progress spinners, and Markdown rendering. Only drop Panel.
- Claude suggested `## header` format over `--- header ---` — agents parse markdown headers better.
- Codex flagged: whitespace stripping scoped too narrowly; tk move needs to handle already-on-branch case; "runs" changes need test updates.
- Claude noted `doctor()` also uses Rich markup and should be simplified.

### Design Update (round 2)
- King overruled the council's suggestion to drop Rich Markdown renderer. The Markdown renderer is good — it gives nice formatted output for humans. The problem is only the Panel boxes.
- Updated approach: `console.print(Markdown(f"## header\n\n{content}"))` — keeps nice rendering, drops box chars.

### Implementation
- Cursor council member actually implemented most changes during its round 2 review (unexpected but useful — council agents can write code during exploration).
- Remaining work: fixed per-line whitespace stripping (body.rstrip() → per-line stripping), removed dead variables (test_style, ruff_style), updated remaining "run" → "session" terminology in state.py, fixed 4 test assertions.
- All 459 tests pass. Ruff clean.

### kd Workflow Experience Notes
**What worked well:**
- `kd tk ready` → scan tickets → `kd tk move` → pull into branch: intuitive flow.
- `kd council ask` provides genuinely useful multi-perspective feedback. Having 3 agents review a design catches edge cases a single reviewer misses (codex caught whitespace scoping, claude caught dead variables, cursor just went ahead and implemented it).
- `kd tk close` is simple and satisfying. Closing 8 tickets at once was smooth.
- The ticket format (`kin-XXXX [P#][status] - title`) is scannable and agent-friendly.

**What was clunky:**
- `kd tk move <id> <branch>` requiring explicit branch name when you're already on that branch — experienced kin-3f60 firsthand. Now fixed.
- Pre-commit hook catching trailing whitespace in council output 3 times in one session — each time requiring re-stage + re-commit. Now fixed via per-line stripping in add_message().
- Council output itself uses Panel boxes (ironic for a PR about removing them). The council watch output wraps responses in `╭──╮` boxes — the very thing we're removing from regular CLI output. This is hardcoded in the council watch flow and wasn't changed here (it's the live display, not persisted output).
- `kd design` printing absolute paths meant I couldn't copy-paste the path directly. Now fixed.

**For agents specifically:**
- The `kd start` → `kd design` → `kd council ask` → `kd tk move` → work → `kd tk close` lifecycle is clear and linear. An agent could follow this with minimal prompting.
- The main friction point for agents is that `kd council ask` output is wrapped in Rich panels — the response text is useful but the box-drawing chars in the output would pollute an agent's context window. This PR fixes that for regular CLI commands but the council watch display (live streaming) still uses panels.
- `kd tk show` not having the file path (now fixed) was a real blocker — agents need to know where to find the file to read or edit it.
