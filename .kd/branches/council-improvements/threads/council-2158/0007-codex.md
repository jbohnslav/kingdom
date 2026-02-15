---
from: codex
to: king
timestamp: 2026-02-15T18:28:30Z
---

Using the `kingdom` skill for this review because you asked for design-vs-implementation and ticket-state assessment through `kd`. I’ll first collect `kd design`, `kd tk list`, current branch status, and targeted code/test evidence, then I’ll map findings to ticket actions (close/reopen/backlog) and run the minimum integration checks.
I found a mismatch: `kd status` reports 14 closed tickets, while `kd tk list` returned none. I’m checking ticket-list filters/help and the underlying `.kd` ticket files to determine actual branch state before making close/reopen decisions.
I’ve confirmed tickets exist but a few closed tickets still show unchecked acceptance boxes, so I’m now validating actual implementation in code/tests and running CLI-level checks before deciding whether any ticket should be reopened.
I’m now validating the most important correctness risk against current code: whether timed-out partial responses are still treated as “successful” (which would violate design intent for reliable retry/status).
I’m running the CLI against the real branch data now (`status`, `list`, `show`, and targeted `retry`) to verify behavior in practice and determine whether we should reopen branch tickets versus only log backlog follow-ups.
I’ve validated the main CLI surfaces manually; next I’m running the key automated suites for council/thread/ticket behavior to ground the recommendation in actual execution rather than static reading.
I’m verifying one more suspected issue before deciding reopen actions: whether “running” status can go stale due leftover `.stream` files even when no new output is arriving.
I’ve run the safe integration paths. I’m now checking `kd tk` capabilities to reopen and append worklog exactly as requested, then I’ll apply only the ticket-state changes backed by concrete bugs.
I confirmed a concrete branch bug against ticket 6412 scope (partial-timeout responses are treated as successful, so retry/status miss failures). I’m reopening `6412` and appending a worklog entry through `kd` now, with the exact reproduction evidence.
`6412` is reopened. The first non-interactive `kd tk edit` attempt failed due shell quoting, so I’m retrying with a simplified editor command to append the worklog entry safely.
The second attempt also failed because `$0` was expanded before `kd` invoked the editor. I’m switching to a temporary `/tmp` editor script (passed through `kd tk edit`) to append the worklog deterministically.
I confirmed `kd council watch` works end-to-end against a live thread and displays stream previews. I’m doing one last backlog scan for already-existing tickets on any additional gaps before final recommendations.
I’ve completed the review and ticket action. I’m pulling exact line references for the core mismatch points, then I’ll give the final assessment and recommendations.
**Findings**
1. High: `timeout + partial text` is still treated as success, so retry/status can miss real failures.
`AgentResponse.thread_body()` returns text when both text and error exist (`src/kingdom/council/base.py:26`), while retry/status depend on error markers in body (`src/kingdom/cli.py:1148`, `src/kingdom/thread.py:396`).

2. High: automatic retry currently excludes timeouts, which conflicts with 6412’s intended behavior.
`NON_RETRIABLE_PREFIXES` includes `"Timeout after"` (`src/kingdom/council/base.py:90`).

3. Medium: ticket/process consistency drift.
Some closed tickets still have unchecked/blank acceptance criteria (`.kd/branches/council-improvements/tickets/549b.md`, `.kd/branches/council-improvements/tickets/e756.md`, `.kd/branches/council-improvements/tickets/41fb.md`).

**Actions Taken**
1. Reopened ticket `6412` via `kd tk reopen 6412`.
2. Added review evidence to worklog in `.kd/branches/council-improvements/tickets/6412.md`.
3. Did not open a new backlog ticket for partial-timeout metadata because existing backlog ticket `9124` already tracks it.

**Design/Plan Alignment**
1. Strong alignment on most Phase 0/1 work: stream-json plumbing, watch streaming UX, richer status, show pagination/turns, list enrichment, per-member reset, retry command.
2. Not fully aligned on 6412 reliability intent due timeout handling gap above.
3. Phase 2/3 items remain backlog by design (`3e60`, `27ce`, `e880`, `1e3d`), so that part is expected.

**Feature Verification**
1. CLI integration checks run: `kd council status --all`, `kd council list`, `kd council show --last/--all`, `kd council retry council-f30b`, `kd council watch council-2158 --timeout 1`.
2. Targeted automated coverage run:
`pytest tests/test_agent.py tests/test_council.py tests/test_thread.py tests/test_cli_council.py tests/test_cli_ticket.py -q`
Result: `257 passed`.

**Code Quality**
1. Overall code quality is good: clear modularization, solid parser/extractor split, and good test density.
2. Main simplification opportunity: centralize “response is failure” classification in one shared helper used by both retry and thread status (currently duplicated policy).
