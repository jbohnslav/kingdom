---
id: "bd1f"
status: open
deps: []
links: []
created: 2026-03-06T14:12:04Z
type: task
priority: 2
parent: b1de
---
# Expand kd doctor to catch agent runtime/auth failures, not just installed CLIs

## Acceptance Criteria

- [ ] Doctor distinguishes missing executables, failed version probes, runtime/authentication failures, and invalid configured model/effort combinations.
- [ ] Checks are scoped to configured agents, so an intentionally unavailable or disallowed backend is not treated as required merely because it is a built-in zero-config option.
- [ ] Account-visible provider catalogs are queried when the CLI exposes them; provider-inherited selections remain unpinned, and unavailable discovery is reported as unchecked rather than guessed.
- [ ] New provider model IDs do not require a Kingdom release unless the provider changes its CLI contract or capability shape.
- [ ] Human and JSON output identify the configured backend, model/effort source, CLI version, and actionable recovery without exposing credentials.
- [ ] Focused regressions cover Claude, Codex, and Cursor success, unavailable, authentication-failure, and catalog-drift paths.

## Worklog

- [2026-08-03 15:47] [codex:a775e044] — Audit on 2026-08-03 during e8cc reconciliation: this ticket remains unresolved. It was intentionally left open; no lifecycle change was made.
- [2026-08-03 15:47] [codex:a775e044] — Current `kd doctor` covers CLI installation/probe failures, config validation, and repository metadata checks. Runtime authentication failures are handled fail-fast by completed ticket bc0c, but doctor itself does not perform the broader runtime/auth checks requested here.
- [2026-08-24 15:05] [king] — Scope refined from dogfood: work environments may intentionally configure Cursor instead of Codex, while Claude, Cursor, and Codex continuously change their account-visible models and CLI capabilities. Reliability means honoring the configured backend set and live provider capabilities, not hardcoding whichever models happen to be current in Kingdom.
