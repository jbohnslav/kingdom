---
id: "d1fa"
status: closed
deps: []
links: [0240]
created: 2026-03-05T16:22:24Z
type: task
priority: 1
assignee: peasant-d1fa
---
# Replace bash hook script with `kd hook run` subcommand

The kingdom hook logic currently lives in a bash script (`.claude/hooks/kd-workflow.sh`), which is gitignored, invisible in worktrees, and doesn't exist after `uv tool install kingdom-cli` on a fresh machine. Replace the bash script entirely with a `kd hook run` Python subcommand that ships with the package. `kd plugin enable` writes `kd hook run` as the hook command in settings.json — resolved from PATH at runtime, works anywhere `kd` is installed.

## Acceptance Criteria

- [ ] New `kd hook run` subcommand reads hook payload JSON from stdin, dispatches by event type, writes JSON to stdout
- [ ] SessionStart handler emits behavioral brief via `additionalContext`
- [ ] UserPromptSubmit handler emits enforcement reminder via `additionalContext`
- [ ] PostToolUse handler sets per-session turn-state flags (`had_work`, `did_log`)
- [ ] Stop handler checks active ticket (`kd tk current`), blocks if `had_work && !did_log && has_ticket`, fail-open on all errors
- [ ] `kd plugin enable` writes settings.json with `kd hook run` as the command for all hook events (no bash path)
- [ ] `kd plugin disable` unchanged
- [ ] `kd plugin status` reports correctly with new command format
- [ ] `.claude/hooks/kd-workflow.sh` deleted — all logic in Python
- [ ] Tests cover all event handlers, state lifecycle, enable/disable, and fail-open behavior
- [ ] Works after `uv tool install kingdom-cli` on a fresh machine with no kingdom source checkout

## Worklog

- 2026-03-05 12:12 — Peasant iteration 1: moved canonical kd-workflow.sh to src/kingdom/hooks/ (tracked in git), updated plugin_enable to call sync_hook_script() which copies tracked source to .claude/hooks/ on enable. All 1633 tests passed.
- 2026-03-05 14:01 — Peasant iteration 2: added kingdom.hooks to pyproject.toml package-data, created __init__.py, removed .claude/hooks/kd-workflow.sh from git, added .gitignore entry. Council approved. All 1634 tests passed.
- 2026-03-05 14:19 — Peasant work rejected: implemented bash-script-move design, but conversation evolved to `kd hook run` Python subcommand approach after discovering the bash path breaks on fresh `uv tool install` machines. Worktree cleaned up, session marked failed.
- 2026-03-05 — Design pivot: replace bash script entirely with `kd hook run` Python subcommand. Hook command in settings.json is just `kd hook run`, resolved from PATH at runtime. No copy/sync mechanism needed. No backward compatibility — new branch, no existing users.
- 2026-03-05 14:27 — Rewrote ticket spec: replaced bash-script-move AC with kd hook run Python subcommand design. All hook logic moves to Python, shipped with package, resolved from PATH. No sync/copy mechanism, no backward compat. Ready for implementation.
- [14:29] — Iteration 1/50 — calling agent
  Ticket: Replace bash hook script with `kd hook run` subcommand
- 2026-03-05 14:38 — Replaced bash hook script with Python kd hook run subcommand. Created src/kingdom/cli/hook.py with handlers for all 4 events (SessionStart, UserPromptSubmit, PostToolUse, Stop). Changed HOOK_COMMAND to 'kd hook run' in plugin.py. Deleted .claude/hooks/kd-workflow.sh. Rewrote all tests to call Python handlers directly — 73 tests covering all events, state lifecycle, fail-open, multi-session isolation, CLI integration. Full suite: 1639 passed. No bash, no file sync — works from PATH after uv tool install.
- [14:39] — The ticket has been completely rewritten — it's no longer about moving a bash script, it's about replacing the bash script entirely with a `kd hook run` Python subcommand. Let me read the current state of the worktree and ticket.The worktree is clean (previous commits were wiped). The ticket is n...
- [14:39] — Files changed:
  .claude/hooks/kd-workflow.sh | 127 -------------
   src/kingdom/cli/__init__.py  |   2 +
   src/kingdom/cli/hook.py      | 210 +++++++++++++++++++++
   src/kingdom/cli/plugin.py    |   2 +-
   tests/test_cli_plugin.py     | 344 ++--------------------------------
   tests/test_hook.py           | 432 +++++++++++++++++++++++++++++++++++++++++++
   tests/test_stop_blocker.py   | 159 ++++++++--------
   7 files changed, 739 insertions(+), 537 deletions(-)
- [14:40] — Council review: BLOCKING (bounce 1/3) — returning to working
  [codex] BLOCKING: Using the `kingdom` skill for this review because it’s a `kd` workflow/CLI change. I’ll validate the exact `b1d73d9` diff in the ticket worktree, then run full tests and lint before giving a verdict.
  [claude] APPROVED: Let me read the diff and key files.Now let me check the plugin.py change and the test_cli_plugin.py / test_stop_blocker.py changes.Clean — just the one-line change. Now the test files.The old bash-based tests are removed. Let me check the test_stop_blocker.py changes.Now let me verify the bash script is fully deleted and check for any remaining references to it.Good — no leftover references. Let me also check that `HOOK_SOURCE` and `sync_hook_script` from the previous iteration are ...
- [14:40] — Iteration 2/50 — calling agent
  Bouncing on council feedback (1 blocking, 1 approved) — see review above
- 2026-03-05 14:42 — Council bounce fix: wrapped SessionStart and UserPromptSubmit handler output in {"additionalContext": "..."} JSON per Claude Code hook protocol. Tests updated to parse and validate JSON structure. All 1639 tests pass.
- [14:42] — The council blocked because SessionStart and UserPromptSubmit handlers emit plain text instead of JSON with `additionalContext`. I need to understand the Claude Code hook output format, then fix the handlers to wrap their output correctly. Let me read the current hook.py and check how the old bas...
- [14:42] — Files changed:
  src/kingdom/cli/hook.py |  4 ++--
   tests/test_hook.py      | 27 +++++++++++++++++----------
   2 files changed, 19 insertions(+), 12 deletions(-)
- [14:43] — Council review: APPROVED — awaiting king review
  [claude] APPROVED: Let me review the updated implementation after the bounce fix for `additionalContext` JSON wrapping.The `additionalContext` fix is in place. Let me verify the tests and check the full diff for this round.Good. Now run the tests.All 1639 tests pass. Let me verify the stale files from previous iterations are gone.---
  [codex] APPROVED: Using the `kingdom` skill again for this review since it’s a `kd` CLI workflow change. I’ll verify the two-commit stack (`b1d73d9` + `399f9ec`) against the acceptance criteria, then re-run tests/lint before final verdict.
