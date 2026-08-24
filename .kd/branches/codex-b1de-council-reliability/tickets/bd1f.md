---
id: "bd1f"
status: closed
deps: []
links: []
created: 2026-03-06T14:12:04Z
type: task
priority: 2
closed_at: 2026-08-24T19:52:04Z
resolution: completed
closed_context: codex:f1fe48bc0e4e0556
assignee: kingdom:49bbdf3beec87570
parent: b1de
---
# Expand kd doctor to catch agent runtime/auth failures, not just installed CLIs

## Acceptance Criteria

- [x] Doctor distinguishes missing executables, failed version probes, runtime/authentication failures, and invalid configured model/effort combinations.
- [x] Checks are scoped to configured agents, so an intentionally unavailable or disallowed backend is not treated as required merely because it is a built-in zero-config option.
- [x] Account-visible provider catalogs are queried when the CLI exposes them; provider-inherited selections remain unpinned, and unavailable discovery is reported as unchecked rather than guessed.
- [x] New provider model IDs do not require a Kingdom release unless the provider changes its CLI contract or capability shape.
- [x] Human and JSON output identify the configured backend, model/effort source, CLI version, and actionable recovery without exposing credentials.
- [x] Focused regressions cover Claude, Codex, and Cursor success, unavailable, authentication-failure, and catalog-drift paths.

## Worklog

- [2026-08-03 15:47] [codex:a775e044] — Audit on 2026-08-03 during e8cc reconciliation: this ticket remains unresolved. It was intentionally left open; no lifecycle change was made.
- [2026-08-03 15:47] [codex:a775e044] — Current `kd doctor` covers CLI installation/probe failures, config validation, and repository metadata checks. Runtime authentication failures are handled fail-fast by completed ticket bc0c, but doctor itself does not perform the broader runtime/auth checks requested here.
- [2026-08-24 15:05] [king] — Scope refined from dogfood: work environments may intentionally configure Cursor instead of Codex, while Claude, Cursor, and Codex continuously change their account-visible models and CLI capabilities. Reliability means honoring the configured backend set and live provider capabilities, not hardcoding whichever models happen to be current in Kingdom.
- [2026-08-24 15:40] [kingdom:49bbdf3b] — Native subagent began regression-first implementation; inspecting current doctor providers and tests while avoiding the concurrent council no-session ticket afd2.
- [2026-08-24 15:44] [kingdom:49bbdf3b] — Added focused regression coverage in `tests/test_cli_doctor_agents.py` for active configured-agent scoping, version/missing/runtime/auth classification across Claude/Codex/Cursor, live Codex/Cursor catalog drift, inherited selections, and unavailable discovery. Confirmed the regression suite fails before implementation at collection because `AgentRuntimeCheck` and `check_agent_runtime` do not yet exist.
- [2026-08-24 15:49] [kingdom:49bbdf3b] — Implemented the bounded doctor runtime slice in `src/kingdom/cli/config.py` and `src/kingdom/cli/__init__.py`, with regressions in `tests/test_cli_doctor_agents.py` and compatibility assertions in `tests/test_cli.py`. Doctor now checks only agents referenced by council/review/peasant/lord configuration; separates missing, version_failed, runtime_failed, and authentication_failed; reports credential-free version/recovery metadata; validates pinned Codex/Cursor selections from account-visible catalogs; and leaves inherited or undiscoverable selections unchecked.

  Verification: `uv run pytest tests/test_cli.py tests/test_cli_doctor_agents.py tests/test_cli_doctor_repository.py -q` passed 77 tests. Focused Ruff check and format check passed for all four changed Python files, and `git diff --check` passed. Manual `uv run kd doctor` and `uv run kd doctor --json` both produced clear backend/version/model/effort-source/recovery output and intentionally exited 1 because this environment's Claude status reports logged out; configured Codex models were discovered as available. No credentials appeared. Full suite was not run per owner handoff direction.
- [2026-08-24 15:52] [codex:f1fe48bc] — Owner review complete. Final combined verification passed: uv run pytest (2272 passed, 41 skipped, 1 xfailed), repository-wide Ruff check and format check, git diff --check, installed provider command help checks, and manual credential-free human/JSON doctor output.

## Lifecycle

- 2026-08-24T19:52:04Z [codex:f1fe48bc0e4e0556] — closed (completed)
