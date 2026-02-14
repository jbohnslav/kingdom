---
from: codex
to: king
timestamp: 2026-02-14T05:30:51Z
---

Using the `kingdom` skill in read-only mode for this review. I’ll inspect the branch diff against `master`, map each change to the 7 tickets, and then assess acceptance criteria, code quality, edge cases, and test coverage ticket-by-ticket.
I’ve identified the exact ticket-related commits. Next I’m reading the actual code/test diffs for the 7 implementation tickets (ignoring `.kd` bookkeeping files) and then I’ll evaluate each ticket against its acceptance criteria.
I’m now in detailed review mode and I’ve already found at least one concrete regression in `kd status --json` output formatting. I’m finishing a pass over command construction and tests to separate hard bugs from weaker test coverage gaps before giving the final ticket-by-ticket verdict.
**Findings (ordered by severity)**
1. High: `kd status --json` currently prints JSON twice, making output invalid for machine consumers. There are two `if output_json` print paths in `src/kingdom/cli.py:1863` and `src/kingdom/cli.py:1882`.
2. Medium: `101d` is not fully complete per its own acceptance criteria; the “no file modifications during council query” check is still unchecked in `.kd/branches/ready-tickets-batch/tickets/101d.md:18`.
3. Medium: Claude read-only tool restriction may be malformed. `build_claude_command()` appends `--allowedTools` plus multiple separate args in `src/kingdom/agent.py:270`; existing workflow examples pass one quoted value string in `.github/workflows/claude.yml:46`.
4. Medium: `whoami`/`status` fallback role detection only recognizes “hand” via `CLAUDECODE`, so non-Claude hand sessions can be misclassified as `king` (`src/kingdom/cli.py:1982`, `src/kingdom/cli.py:1871`).
5. Low: docs drift for `c5cb`: README still advertises removed `kd breakdown --apply` at `README.md:35`.

**Ticket-by-ticket assessment**

1. `c5cb`
- Acceptance criteria: Mostly satisfied (breakdown parser/apply logic removed; prompt-based flow implemented).
- Code quality: Clean/minimal in `src/kingdom/cli.py:845` and `src/kingdom/breakdown.py:1`.
- Bugs/edges: Behavior/docs mismatch remains (`README.md:35`).
- Tests: Partial. Updated tests exist (`tests/test_breakdown.py:1`, `tests/test_cli_design_breakdown.py:25`), but no test explicitly verifies `--apply` is gone or that output includes `kd tk dep`.

2. `8af5`
- Acceptance criteria: Functionally satisfied in `src/kingdom/cli.py:240` with `--force` at `src/kingdom/cli.py:211`.
- Code quality: Simple and consistent.
- Bugs/edges: Next-step hint is a bit underspecified (`kd tk move` without explicit `--to backlog`) at `src/kingdom/cli.py:248`.
- Tests: Inadequate. No new coverage in `tests/test_done.py` for open-ticket failure path or `--force`.

3. `101d`
- Acceptance criteria: Partially satisfied; prompt + permission config were added, but the no-modification validation is not done (`.kd/branches/ready-tickets-batch/tickets/101d.md:18`).
- Code quality: Reasonable, but Claude allowedTools construction is risky (`src/kingdom/agent.py:270`).
- Bugs/edges: Potential command-shape issue for Claude read-only enforcement; could fail or not enforce as intended.
- Tests: Partial only (`tests/test_agent.py:321`, `tests/test_council.py:39`). No integration check that council queries leave filesystem unchanged.

4. `98fe`
- Acceptance criteria: Satisfied in code (`src/kingdom/cli.py:190`, `src/kingdom/cli.py:205`).
- Code quality: Minimal and idiomatic.
- Bugs/edges: None obvious.
- Tests: Inadequate. No dedicated `kd start` assertions for template population/path output in `tests/test_init.py`.

5. `98f3`
- Acceptance criteria: Satisfied, including cross-filesystem fallback (`src/kingdom/ticket.py:383`).
- Code quality: Good, small change.
- Bugs/edges: `except OSError` is broad; fallback could mask non-EXDEV rename errors (`src/kingdom/ticket.py:385`).
- Tests: Good coverage added (`tests/test_ticket.py:828`, `tests/test_cli_ticket.py:405`).

6. `e4b1`
- Acceptance criteria: Partially satisfied; assignment display added, but JSON output is broken and “assigned-to-me + file locations” is not fully implemented (`src/kingdom/cli.py:1863`, `src/kingdom/cli.py:1882`, `src/kingdom/cli.py:1899`).
- Code quality: Needs cleanup due duplicated JSON path.
- Bugs/edges: Critical JSON regression as above.
- Tests: Inadequate; `tests/test_cli_status.py:58` only checks substring presence and would not catch invalid JSON.

7. `2819`
- Acceptance criteria: Mostly satisfied (new command + env plumbing in `src/kingdom/cli.py:1974`, `src/kingdom/council/base.py:100`, `src/kingdom/harness.py:331`).
- Code quality: Minimal.
- Bugs/edges: Fallback role detection is too Claude-specific (`src/kingdom/cli.py:1982`).
- Tests: Missing. No `whoami` command tests and no tests for env injection behavior.

**Assumptions / limits**
- Review was static (read-only), based on code and tests diff; I did not execute test runs.
