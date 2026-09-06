---
id: "dcab"
status: open
links: []
created: 2026-09-05T23:42:47Z
type: task
priority: 2
deps: ["79a4", "80d2"]
parent: "1465"
---
# Consolidate streaming hook normalization and message status handling

Implement audit findings 13–15 after current-format state is established.

Use one small streaming subprocess implementation for peasant and lord loops, with explicit incremental log flushing, clear error reporting, concurrent stdout/stderr draining, and correct shutdown. Avoid a runner class hierarchy. Normalize provider hook payloads once at the CLI boundary; internal handlers consume HostEvent instead of HostEvent | dict. Use one current-message status interpretation across thread status, TUI history, and council retry, and remove missing-member-state fallbacks that only incomplete test objects produce.

Keep the real provider-format distinctions at ingress and preserve interruption, timeout, and error behavior. When fixing an actual bug discovered in the duplicate paths, add a failing behavioral regression before the fix.

## Acceptance Criteria

- [ ] Peasant and lord share one streaming function and live output is flushed visibly during execution.
- [ ] Hook normalization occurs once at ingress; handler tests use normalized events and ingress tests cover provider payloads.
- [ ] Thread/TUI/retry agree on current message status with no synthetic backward-compatibility fallback.
- [ ] Meaningful streaming, error, interruption, and shutdown tests cover the shared path.
- [ ] Full suite including Textual integration and Ruff pass; watch output is manually verified using controlled local subprocesses.

## Worklog

- 2026-09-05 — Scoped from the King’s request for the full six-area cleanup; historical closed-ticket compatibility is not a preservation requirement.
- [2026-09-05 19:54] [codex:a65a16d5] — Preparation confirms streaming implementations diverge: peasant reopens the live log for each line; lord holds a buffered log open without explicit per-line flush. Both suppress write errors. Consolidation must retain concurrent stdout/stderr draining, make live output observable before child exit, and report logging errors without losing subprocess cleanup. Use a real controlled child-process regression for incremental visibility.
- [2026-09-05 20:06] [codex:a65a16d5] — Native streaming slice committed as 94551e6 for review/integration after runtime cleanup. Real child regression failed old lord implementation with exit 17 because live log output was buffered until exit; shared function passes. Nine behavioral tests cover incremental visibility, full pipes, capture, log/decode failures and interrupt cleanup. Agent full suite: 2356 passed, 3 old skips, 1 old xfail; Ruff/hooks passed. Independent review assigned before integration.
- [2026-09-05 20:09] [codex:a65a16d5] — Independent streaming review found a descendant-pipe shutdown hang: killing only the direct child left drain threads waiting for inherited pipe handles. Follow-up dcee42d adds separate process-session launch and process-group termination on failure/interruption. Descendant regressions failed for log-write and KeyboardInterrupt paths before fix, then passed; agent full suite 2358 passed, 3 old skips, 1 old xfail. Reviewed scope stays one function and preserves meaningful process cleanup.
- [2026-09-05 20:11] [codex:a65a16d5] — Root added and ran failing retry regression: latest codex message status=error after an earlier complete response makes thread status errored, but council retry says Nothing to retry. Saved regression patch for dcab integration; fix will use the same latest-message status calculation as thread status, preserving targeted ask filtering. This is a real consistency bug, not only synthetic-state cleanup.
- [2026-09-05 20:14] [codex:a65a16d5] — Hook normalization preparation ca73b5f removes handler_event and internal dict acceptance; tests construct normalized HostEvent fields directly. Raw cwd fallback moved to CLI ingress; malformed direct-handler case removed while provider/lifecycle integration remains covered. Agent targeted 121 tests pass, whole-tree Ruff/hooks pass. Integration will use this commit only, not its temporary runtime snapshot parent.
