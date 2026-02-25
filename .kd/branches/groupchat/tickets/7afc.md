---
id: "7afc"
status: open
deps: [27ce]
links: []
created: 2026-02-16T18:50:43Z
type: task
priority: 2
---
# Group chat modes: natural, round_robin, manual, broadcast

## Acceptance Criteria

- [ ] `natural` mode (default): first turn parallel broadcast, then shuffled round-robin for `auto_rounds` rounds
- [ ] `round_robin` mode: no initial broadcast, fixed config-order sequential turns for `auto_rounds` rounds
- [ ] `manual` mode: every response requires explicit @mention, including first turn; show hint if king sends without @mention
- [ ] `broadcast` mode: every turn fans out to all active members in parallel; `auto_rounds` controls additional parallel rounds
- [ ] Config validation accepts all four modes, rejects unknown values
- [ ] Muted members are excluded from all mode scheduling
