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
