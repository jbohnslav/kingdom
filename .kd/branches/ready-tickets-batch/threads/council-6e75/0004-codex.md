---
from: codex
to: king
timestamp: 2026-02-14T04:44:15Z
---

I’ll do a read-only review of those 9 tickets and produce implementation guidance per ticket, plus dependency/conflict analysis across them. First I’m loading the `kingdom` skill instructions and then I’ll inspect ticket metadata and related code paths.
I’ve loaded the `kingdom` workflow instructions and will use it for this review. Next I’m pulling ticket metadata and dependencies from `kd` for all 9 IDs, then I’ll map each ticket to concrete files and sequencing guidance.
I now have the ticket text and current dependencies. Next I’m mapping each ticket to concrete implementation surfaces by scanning the CLI modules (`start`, `done`, `breakdown`, `council`, `tickets`, `status/whoami`) and current tests.
I’ve located the command implementations; now I’m reading the exact `breakdown`, `ticket move`, `status`, council/agent, and state/config code to identify precise touch points and edge cases.
I have the main code paths. I’m now reviewing existing tests around each command so guidance can include exact expected behavior and likely regression points.
I confirmed the command/test surfaces and found one important context point: this repo currently has no `.kd/agents/*.md` files checked in, so council config is effectively code-defaults today. I’m doing one more pass over branch/workflow docs and relevant command internals, then I’ll give per-ticket implementation guidance plus sequencing/dependency recommendations.
**Ticket Guidance**
1. `c5cb` (`Replace kd breakdown with agent prompt output`): Key files are `src/kingdom/cli.py:828`, `src/kingdom/breakdown.py`, `tests/test_breakdown.py`, `tests/test_cli_design_breakdown.py`, and `README.md`. Approach: keep `kd breakdown` as template/init behavior, remove `--apply` parsing/creation flow, and print a copy/paste prompt telling the agent to read `design.md` and run `kd tk create` + `kd tk dep`. Gotchas: this will intentionally break current `--apply` docs/tests and any automation relying on `parse_breakdown_tickets`; clean those in the same PR.

2. `8af5` (`kd done should error if branch has open tickets`): Key files are `src/kingdom/cli.py:203` and `tests/test_done.py`. Approach: add `--force`, inspect only that target branch’s `tickets/` directory before writing `status=done`, print open/in-progress tickets + next steps, then exit non-zero unless forced. Gotchas: support both `.kd/branches/...` and legacy `.kd/runs/...`, and avoid checking backlog/global tickets.

3. `101d` (`Council members read-only enforcement`): Key files are `src/kingdom/council/base.py:39`, `src/kingdom/agent.py`, `tests/test_council.py`, and `tests/test_cli_council.py`. Approach: strengthen preamble language, enforce read-only command flags per backend where supported, and keep `skip_permissions=False` for council paths. Gotchas: existing tests assert exact command arrays/preamble strings, so they will need updates; read-only must not block normal read tools.

4. `b5aa` (`Enable branch protection on master`): This is mostly GitHub settings, not core Python code. Practical files to touch (optional) are `.github/workflows/ci.yml` (ensure required checks are stable) and a small ops doc/script under `scripts/` or `docs/`. Gotchas: requires repo admin rights; decide whether protected branch is `master` or `main` before applying rules.

5. `3860` (`Add JSON config for system-wide agent/workflow settings`): Key files are `src/kingdom/state.py:228`, `src/kingdom/agent.py`, `src/kingdom/council/council.py`, and likely a new config module plus tests in `tests/test_agent.py`/`tests/test_council.py`. Approach: define one schema for council members/models/permissions/prompt overrides, load once with defaults fallback, and thread config into council/agent construction. Gotchas: `.kd/.gitignore` currently ignores `*.json`, so `.kd/config.json` is untracked; if this config must be shared, use a tracked top-level file or adjust ignore rules.

6. `98fe` (`kd start initializes design doc + prints location`): Key files are `src/kingdom/cli.py:151`, `src/kingdom/design.py:35`, and `tests/test_init.py`. Approach: after `ensure_branch_layout`, populate `design.md` from `build_design_template` only if empty, and print the design doc path explicitly. Gotchas: keep `kd design` idempotent and do not overwrite existing user content on repeated `kd start --force`.

7. `98f3` (`kd tk move removes source location`): Key files are `src/kingdom/cli.py:2473`, `src/kingdom/ticket.py:362`, and `tests/test_cli_ticket.py`. Approach: add regression tests that source file is gone after move and that ambiguous/duplicate states are handled clearly; if bug reproduces, fix lookup/move path, not just move primitive. Gotchas: `move_ticket()` already uses `rename()`; the likely failure is around lookup scope/duplicate IDs, so capture a repro first.

8. `e4b1` (`kd status shows agent workload + assignments`): Key files are `src/kingdom/cli.py:1810`, `src/kingdom/session.py` (`list_active_agents`), `src/kingdom/ticket.py`, and `tests/test_cli_status.py`. Approach: extend existing `kd status` (don’t add a second command name) with assigned-to-me view + optional all-agent assignment/workload section; include JSON fields too. Gotchas: current status tests assert exact simplified output, so either preserve existing lines and append sections or update tests intentionally.

9. `2819` (`Add kd whoami`): Key files are `src/kingdom/cli.py`, `src/kingdom/council/base.py`, `src/kingdom/harness.py:324`, and new tests (likely `tests/test_cli_status.py` or a new `tests/test_cli_whoami.py`). Approach: implement `kd whoami` and propagate explicit identity env vars when spawning council/peasant subprocesses so role detection is deterministic. Gotchas: `kd work` uses `hand-*` session names in some paths, so role mapping should be explicit via env, not inferred only from session name patterns.

**Ordering / Grouping**
1. Foundation config+safety: `3860` then `101d`.
2. Identity/visibility: `2819` then `e4b1` (already declared as dependency).
3. Workflow correctness: `98f3`, `8af5`, `98fe`.
4. Breakdown product shift: `c5cb` (separate PR; broader doc/test churn).
5. Ops/policy: `b5aa` in parallel (manual/admin task).

**Missing Dependencies / Conflicts**
1. Missing dependency candidate: `101d` should likely depend on `3860` if permission rules are meant to be configurable instead of hardcoded.
2. Existing conflict: `e4b1` says “add kd status command,” but `kd status` already exists in `src/kingdom/cli.py:1810`; implement as extension, not a new duplicate command.
3. Existing conflict: `c5cb` will invalidate current `README.md` and tests referencing `kd breakdown --apply`.
4. External dependency: `b5aa` needs GitHub admin permissions and stable required-check names from workflows.
