---
id: "e5dd"
status: open
deps: []
links: []
created: 2026-02-17T03:04:22Z
type: task
priority: 2
---
# Config validation on startup

## Description

Validate config on `load_config()` so errors surface early (on `kd start`, `kd chat`, `kd council ask`, etc.) instead of crashing mid-operation. Currently config loading silently accepts bad keys.

## Acceptance Criteria

- [ ] `load_config()` validates by default — unknown keys, bad types, invalid values raise clear errors
- [ ] Validation covers all sections (agents, council, peasant, prompts)
- [ ] Error messages include the key path and what's wrong (e.g. "Unknown key 'council.foo'")
- [ ] Existing valid configs continue to load without error
- [ ] Test: config with unknown keys raises ValueError
- [ ] Test: config with bad types raises ValueError
- [ ] Test: empty/missing config loads defaults without error
