---
id: "5afc"
status: closed
deps: [4c83]
links: []
created: 2026-02-27T11:55:19Z
type: task
priority: 1
closed_at: 2026-02-27T14:46:52Z
---
# Redesign command surface (R1)

## Problem

The CLI surface has accumulated commands that should be deleted, merged, or reorganized. This must happen while still in one file so the full picture is visible.

## Acceptance Criteria

- [ ] Delete commands: `init`, `dev`, `work`, `whoami`, `migrate`, `chat` (top-level), `breakdown`, `setup-skill`
- [ ] Fold `setup-skill` behavior into `kd start` (auto-setup when `.kd/` missing or skill not installed)
- [ ] Fold `init` behavior into `kd start` (auto-init `.kd/` if not present)
- [ ] Move `chat` to `kd council chat`
- [ ] Create `kd tk deps` sub-app with `add`, `remove`, `tree`, `cycle`; delete old `dep`, `undep`, `dep-tree`, `dep-cycle`
- [ ] Remove standalone `kd tk ready`, `kd tk closed`, `kd tk blocked`, `kd tk query`
- [ ] Add `--ready`, `--closed`, `--blocked`, `--json`, `--jq` flags to `kd tk list`
- [ ] `--json` outputs ticket schema (non-closed by default); `--jq EXPR` applies a jq filter; `--closed` includes closed tickets in JSON output
- [ ] `kd design` prints path, `kd design show` renders in terminal, `kd design approve` kept
- [ ] Replace `kd peasant review --accept` / `--reject` with `kd peasant accept <id>` and `kd peasant reject <id> "feedback"` — these are distinct actions, not flags on a review command
- [ ] Hidden aliases retained: `kd tk ls` → `kd tk list`, `kd council ls` → `kd council list`
- [ ] All tests updated to reflect new command surface
- [ ] All tests pass

## Worklog

- 2026-02-27 14:33 — Reopened: 'delete kd work' acceptance criterion was correct after all. The current implementation uses kd work as a hidden CLI command that's a subprocess entry point for peasant launch — but that's a bad pattern. We're writing Python, not shelling out to our own CLI. Fix: delete kd work, create a kingdom/worker.py entry point (or __main__ block in harness.py) that launch_work_background/launch_work_tmux invoke directly via python -m kingdom.worker. The interactive hand-mode context resolution stays in peasant_start. Also fix: kd start error message still references deleted 'kd init --no-git' command (cli.py:219).
