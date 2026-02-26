---
id: "7afc"
status: closed
deps: [27ce]
links: []
created: 2026-02-16T18:50:43Z
type: task
priority: 2
closed_at: 2026-02-25T04:41:38Z
---
# Group chat modes: natural, round_robin, manual, broadcast

## Acceptance Criteria

- [x] `natural` mode (default): first turn parallel broadcast, then shuffled round-robin for `auto_rounds` rounds
- [x] `round_robin` mode: no initial broadcast, fixed config-order sequential turns for `auto_rounds` rounds
- [x] `manual` mode: every response requires explicit @mention, including first turn; show hint if king sends without @mention
- [x] `broadcast` mode: every turn fans out to all active members in parallel; `auto_rounds` controls additional parallel rounds
- [x] Config validation accepts all four modes, rejects unknown values
- [x] Muted members are excluded from all mode scheduling

## Worklog

- Changed default chat mode from `broadcast` to `natural`
- Config validation: `{"broadcast", "sequential"}` → `{"natural", "round_robin", "manual", "broadcast"}`
- Refactored `run_chat_round` into mode-specific dispatchers: `run_mode_natural`, `run_mode_round_robin`, `run_mode_manual`, `run_mode_broadcast`
- Extracted shared helpers: `parallel_query` (asyncio.gather), `sequential_auto_turns` (with shuffle param)
- `natural` mode: parallel broadcast → shuffled round-robin auto-turns
- `round_robin` mode: sequential fixed-order through all rounds (no broadcast/auto distinction)
- `manual` mode: only @mentioned targets queried, no auto-turns; notify hint if no @mention
- `broadcast` mode: parallel to all each turn, auto_rounds controls additional parallel rounds
- `send_message` returns text to input area in manual mode when no @mention provided
- 8 new tests: natural, natural-first-exchange, manual, broadcast-auto-rounds, broadcast-first, round-robin-no-broadcast, round-robin-fixed-order, round-robin-muted
- Updated 4 existing config tests
- All 1370 tests pass
