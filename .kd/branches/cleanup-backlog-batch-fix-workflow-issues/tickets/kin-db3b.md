---
id: kin-db3b
status: closed
deps: []
links: []
created: 2026-02-13T14:24:23Z
type: task
priority: 2
---
# Revert council async default, use BASH_DEFAULT_TIMEOUT_MS instead

The recent kin-7bd5 change made `kd council ask` async by default to work around Claude Code's bash timeout killing long-running council queries. The simpler fix is to set `BASH_DEFAULT_TIMEOUT_MS` to 300000 (5 minutes) in CLAUDE.md or the project settings, so `kd council ask` can block synchronously without getting killed. Revert the async-by-default behavior and keep `kd council ask` synchronous (streaming responses as they come in). The `--async` flag can stay as an opt-in for background dispatch.

## Acceptance Criteria

- [ ] `kd council ask` is synchronous by default again (blocks until all responses)
- [ ] CLAUDE.md or project config sets `BASH_DEFAULT_TIMEOUT_MS=300000`
- [ ] `--async` flag remains available for opt-in background dispatch
- [ ] Revert async-related default behavior from kin-7bd5
