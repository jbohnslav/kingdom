---
from: codex
to: king
timestamp: 2026-02-13T13:10:20Z
---

I’ll do a read-only review of the current local implementation and verify behavior against the design intent, focusing on the new unified ticket execution flow and any regressions. I’m starting with unstaged diffs, then targeted tests.
I found substantial CLI changes around `kd work`, `peasant start`, and review relaunch. I’m now checking the exact code paths and running the peasant/work tests to verify whether this actually works end-to-end or regressed.
I confirmed regressions in the peasant test suite after this implementation. I’m now comparing the code against your current design doc to verify whether behavior matches the intended `kd work`/`peasant` model and to identify functional gaps beyond the failing tests.
I’m also checking for collateral changes and running adjacent suites (`cli` + `harness`) to determine whether the new `kd work` path is stable or only partially integrated.
I’ve confirmed `kd work` is wired into the CLI and core harness tests pass, but there are clear integration gaps in peasant review/start tests. I’m doing a final targeted scan for missing coverage and behavior mismatches against the design before I give you the review findings.
I’ve identified at least one functional mismatch with the design (`kd work` context resolution) beyond the test regressions. I’m running the full test suite quickly to quantify current stability and check if there are additional breakages.
I’ve confirmed broader instability from the unstaged changes (10 failing tests total). I’m doing one direct behavioral check for `kd work --base` to verify whether the new command really works outside the repo root/worktree context as intended.
I’ve finished validation. I’m collecting exact line references for the concrete failures and then I’ll give you a concise review with severity ordering and what’s broken vs aligned with design.
**Findings**

1. **High**: `kd work` interactive path does not honor `--base` and resolves tickets from `cwd`, which breaks the “run from any workspace” design.
- Evidence: `src/kingdom/cli.py:1699` calls `_resolve_peasant_context(ticket_id)`, and `_resolve_peasant_context` hardcodes `base = Path.cwd()` at `src/kingdom/cli.py:979`.
- Repro I ran: `cd /tmp && python -m kingdom.cli work kin-41f9 --base /Users/jrb/code/kingdom` -> `Ticket not found: kin-41f9`.
- Design mismatch: `.kd/branches/peasant-worktree-optional/design.md:7` and `.kd/branches/peasant-worktree-optional/design.md:29`.

2. **High**: Unasked council prompt mutation changes all council command payloads and currently breaks council contract tests.
- Evidence: global preamble injection in `src/kingdom/council/base.py:38` and `src/kingdom/council/base.py:52`.
- Result: multiple failures in `tests/test_council.py` (expected raw prompt command shapes at `tests/test_council.py:29`, `tests/test_council.py:35`, `tests/test_council.py:48`, `tests/test_council.py:61`, `tests/test_council.py:77`, `tests/test_council.py:84`, `tests/test_council.py:122`).

3. **Medium**: Launcher refactor removed `launch_harness`, causing peasant review relaunch tests to fail and reducing testability.
- Evidence: relaunch logic now duplicated inline in `src/kingdom/cli.py:1534` and start path duplicates subprocess launch in `src/kingdom/cli.py:1066`; old helper no longer exists.
- Failures: `tests/test_cli_peasant.py:802`, `tests/test_cli_peasant.py:840`, `tests/test_cli_peasant.py:862` patch a symbol that no longer exists.

4. **Medium**: `agent` command group is now empty (backward-compatibility/UX regression).
- Evidence: group still registered at `src/kingdom/cli.py:1662`, but no subcommands remain.
- `python -m kingdom.cli agent --help` shows no commands.

**Validation I ran**
- `pytest -q` -> **10 failed, 426 passed, 3 skipped**.
- Failures are exactly in `tests/test_cli_peasant.py` (3) and `tests/test_council.py` (7).
- `tests/test_harness.py` and `tests/test_cli.py` still pass.

**What is working as intended**
- `kd work` exists and is wired (`src/kingdom/cli.py:1666`).
- `kd peasant start` now launches `kd work` in background with internal args (`src/kingdom/cli.py:1071`).

1. If you want, I can do a follow-up pass proposing the smallest patch set to restore green tests while keeping the new `kd work` architecture.
