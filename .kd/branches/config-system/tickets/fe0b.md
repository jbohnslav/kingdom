---
id: fe0b
status: open
deps: [d52d, 5151]
links: []
created: 2026-02-14T14:12:21Z
type: task
priority: 2
---
# Wire config into peasant/harness and design/synthesis

Update peasant, design, and synthesis paths to use config instead of hardcoded values.

## Details

- `harness.py`: read peasant agent from `config.peasant.agent` instead of hardcoding claude. Use `config.peasant.timeout` and `config.peasant.max_iterations`. Prepend peasant phase prompt (agent-specific or global) to harness prompts.
- `design.py`: derive council member list from config, not hardcoded `["claude", "codex", "agent"]`.
- `synthesis.py`: `COUNCIL_ORDER` derived from `config.council.members`, not hardcoded. `build_synthesis_prompt` iterates over config members.
- Thread config through from `cli.py` to these modules.

## Acceptance Criteria

- [ ] Peasant agent comes from config (default: claude)
- [ ] Peasant timeout and max_iterations come from config
- [ ] Peasant phase prompt is prepended to harness prompts
- [ ] `design.py` uses config council members, not hardcoded names
- [ ] `synthesis.py` uses config council members, not hardcoded `COUNCIL_ORDER`
- [ ] Tests cover: custom peasant agent, peasant prompts, dynamic council order
